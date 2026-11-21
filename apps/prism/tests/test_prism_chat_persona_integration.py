from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism
from app.schemas.prism_v22 import PrismCreate
from app.services.agent_preference_service import AgentPreferenceService
from app.services.llm_provider import FakeLLMProvider, ProviderResult
from app.services.llm_service import LLMService
from app.services.prism_conversation_service import PrismConversationService
from app.services.prism_lifecycle_service import PrismLifecycleService


def _decision(lookup: bool, reply: str = "") -> ProviderResult:
    return ProviderResult(
        text=json.dumps({"needs_work_lookup": lookup, "reply": reply}), model="fake-model"
    )


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    get_settings.cache_clear()
    with SessionLocal() as db:
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(
                name=f"Priya {uuid.uuid4().hex[:6]}", description="Sales ops lead for the pipeline."
            ),
        )
        for target, event, confirmed in (
            (PrismLifecycleState.ONBOARDING, "onboarding_started", False),
            (PrismLifecycleState.AWAITING_CONFIRMATION, "agreement_prepared", False),
            (PrismLifecycleState.ACTIVE, "agreement_confirmed", True),
        ):
            prism = PrismLifecycleService.transition(
                db,
                prism.id,
                target=target,
                expected_lifecycle_version=prism.lifecycle_version,
                event_type=event,
                agreement_confirmed=confirmed,
            )
        _, thread = PrismConversationService.canonical_thread(db, prism.id)
        AgentPreferenceService.remember_for_prism(
            db, prism_id=prism.id, thread_id=thread.id, instruction="Keep it casual."
        )
        ids = (prism.id, thread.id, prism.name)
    yield ids
    LLMService.provider_override = None
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.execute(delete(AgentThread).where(AgentThread.prism_id == ids[0]))
        db.execute(delete(Prism).where(Prism.id == ids[0]))
        db.commit()


def _messages(thread_id):
    with SessionLocal() as db:
        return [
            (m.role, m.content)
            for m in db.scalars(
                select(AgentThreadMessage)
                .where(AgentThreadMessage.thread_id == thread_id)
                .order_by(AgentThreadMessage.created_at)
            )
        ]


def test_prism_chats_in_character_when_no_work_is_involved(setup) -> None:
    prism_id, thread_id, name = setup
    provider = FakeLLMProvider(
        [_decision(False, "Ha, Monday energy! Coffee first, pipeline later.")]
    )
    LLMService.provider_override = provider
    client = TestClient(app)

    done = client.post(
        f"/api/v2/agent/threads/{thread_id}/chat-reply", json={"content": "ugh mondays"}
    )
    assert done.json() == {"handled": True}
    assert _messages(thread_id)[-1] == (
        "assistant",
        "Ha, Monday energy! Coffee first, pipeline later.",
    )
    seen = provider.requests[0]
    assert f"You are {name}" in seen["prompt"]
    assert "Sales ops lead for the pipeline." in seen["prompt"]
    assert seen["context"]["manager_instructions"] == ["Keep it casual."]
    assert seen["context"]["chat_message"] == "ugh mondays"


def test_work_requests_and_model_failures_still_reach_the_work_flow(setup) -> None:
    _, thread_id, _ = setup
    client = TestClient(app)
    url = f"/api/v2/agent/threads/{thread_id}/chat-reply"

    # The model says this needs Teams: nothing is stored here.
    LLMService.provider_override = FakeLLMProvider([_decision(True)])
    assert client.post(url, json={"content": "how did the launch go"}).json() == {"handled": False}

    # Clear work words never reach the model, so they are never delayed or swallowed.
    provider = FakeLLMProvider([_decision(False, "should not be used")])
    LLMService.provider_override = provider
    assert client.post(url, json={"content": "summarize the last 10 messages"}).json() == {
        "handled": False
    }
    assert provider.requests == []

    # A model failure falls back to the simple replies, and real work is still not swallowed.
    LLMService.provider_override = FakeLLMProvider([])
    assert client.post(url, json={"content": "hi"}).json() == {"handled": True}
    assert client.post(url, json={"content": "how did the launch go"}).json() == {"handled": False}
    assert [role for role, _ in _messages(thread_id)] == ["manager", "assistant"]


def test_questions_about_people_or_work_are_never_answered_as_chat(setup) -> None:
    from app.models.employee import Employee

    _, thread_id, _ = setup
    tag = uuid.uuid4().hex[:6]
    with SessionLocal() as db:
        db.add(
            Employee(
                name=f"Akshay{tag} Aher", email=f"akshay-{tag}@example.com", role="Team member"
            )
        )
        db.commit()
    try:
        provider = FakeLLMProvider(
            [_decision(False, "Hi Akshay, quick check-in on your work.")] * 3
        )
        LLMService.provider_override = provider
        client = TestClient(app)
        url = f"/api/v2/agent/threads/{thread_id}/chat-reply"

        # The real case: a work question that no keyword list would catch.
        for question in (f"has akshay{tag} deployed the writings page?", "has it gone out yet?"):
            assert client.post(url, json={"content": question}).json() == {"handled": False}
        assert provider.requests == []
        assert _messages(thread_id) == []
    finally:
        with SessionLocal() as db:
            db.execute(delete(Employee).where(Employee.email == f"akshay-{tag}@example.com"))
            db.commit()


def test_a_reply_that_is_really_a_message_to_someone_else_is_not_used(setup) -> None:
    _, thread_id, _ = setup
    LLMService.provider_override = FakeLLMProvider(
        [_decision(False, "Hi Akshay, quick check-in on your current work. Any blockers?")]
    )
    client = TestClient(app)
    done = client.post(
        f"/api/v2/agent/threads/{thread_id}/chat-reply", json={"content": "ugh mondays"}
    )
    assert done.json() == {"handled": False}
    assert _messages(thread_id) == []
