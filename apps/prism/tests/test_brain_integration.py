"""The shared brain: user entries, learned facts that wait for approval, and what Prisms are given."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.agent_v21 import AgentThread
from app.models.brain import BrainEntry
from app.services import llm_service
from app.services.brain_service import BrainService, _Fact, _Learned
from app.services.prism_agent_service import PrismAgentService
from tests.test_qa_tester_integration import _active_prism


def _drop(db, prism) -> None:
    db.execute(delete(AgentThread).where(AgentThread.prism_id == prism.id))
    db.delete(prism)
    db.commit()


@pytest.fixture
def clean_brain():
    with SessionLocal() as db:
        db.execute(delete(BrainEntry))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(BrainEntry))
        db.commit()


def test_prisms_only_see_approved_entries(clean_brain):
    with SessionLocal() as db:
        BrainService.create(db, "What we do", "OneClarity builds Prism.")
        pending = BrainEntry(title="Pricing", body="Free beta.", status="proposed", source="chat")
        db.add(pending)
        db.commit()

        assert "OneClarity builds Prism." in BrainService.context(db)
        assert "Free beta." not in BrainService.context(db)

        BrainService.decide(db, pending.id, True)
        assert "Free beta." in BrainService.context(db)

        BrainService.decide(db, pending.id, False)
        assert "Free beta." not in BrainService.context(db)


def test_a_prisms_computer_is_told_what_the_brain_knows(clean_brain):
    with SessionLocal() as db:
        prism = _active_prism(db, "blank", "Researches companies.")
        BrainService.create(db, "What we do", "OneClarity builds Prism.")
        assert "OneClarity builds Prism." in PrismAgentService.instructions(db, prism)
        _drop(db, prism)


def test_chat_facts_are_proposed_not_used_until_approved(clean_brain, monkeypatch):
    seen = {}

    def fake(*, prompt, context, output_model, feature, **_):
        seen.update(context)
        return _Learned(
            facts=[
                _Fact(title="Our ICP", body="Series A fintech in India."),
                _Fact(title="our icp", body="duplicate"),
            ]
        )

    monkeypatch.setattr(llm_service.LLMService, "complete", staticmethod(fake))
    with SessionLocal() as db:
        prism = _active_prism(db, "blank", "Researches companies.")
        assert BrainService.learn(db, prism, "Short") == 0
        added = BrainService.learn(
            db, prism, "Our ideal customer is a Series A fintech company in India, please remember"
        )
        assert added == 1
        assert "Series A" not in BrainService.context(db)
        rows = BrainService.list(db)
        assert [(r.status, r.source) for r in rows] == [("proposed", "chat")]
        _drop(db, prism)


def test_a_prisms_work_note_is_shared_and_replaced(clean_brain):
    with SessionLocal() as db:
        prism = _active_prism(db, "blank", "Researches companies.")
        BrainService.note_work(db, prism, "Fintech list", "Found 10 companies.")
        BrainService.note_work(db, prism, "Fintech list", "Found 20 companies.")
        context = BrainService.context(db)
        assert "What the other Prisms are working on" in context
        assert "Found 20 companies." in context
        assert len(BrainService.list(db)) == 1
        _drop(db, prism)


def test_brain_api_round_trip(clean_brain):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    created = client.post("/api/v2/brain", json={"title": "Tone", "body": "Friendly."})
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert (
        client.patch(f"/api/v2/brain/{entry_id}", json={"body": "Warm."}).json()["body"] == "Warm."
    )
    assert [e["title"] for e in client.get("/api/v2/brain").json()] == ["Tone"]
    assert client.delete(f"/api/v2/brain/{entry_id}").status_code == 204
    assert client.get("/api/v2/brain").json() == []
    assert client.delete(f"/api/v2/brain/{uuid.uuid4()}").status_code == 404


def test_only_an_archived_prism_can_be_deleted(clean_brain):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.enums import PrismLifecycleState
    from app.models.prism_v22 import Prism
    from app.services.prism_conversation_service import PrismConversationService
    from app.services.prism_lifecycle_service import PrismLifecycleService

    client = TestClient(app)
    with SessionLocal() as db:
        prism = _active_prism(db, "blank", "Researches companies.")
        PrismConversationService.canonical_thread(db, prism.id)
        BrainService.note_work(db, prism, "Fintech list", "Found 10 companies.")
        prism_id = prism.id
        version = prism.lifecycle_version

    assert client.delete(f"/api/v2/prisms/{prism_id}").status_code == 422
    with SessionLocal() as db:
        PrismLifecycleService.transition(
            db,
            prism_id,
            target=PrismLifecycleState.ARCHIVED,
            expected_lifecycle_version=version,
            event_type="archived",
        )
    assert client.delete(f"/api/v2/prisms/{prism_id}").status_code == 204
    with SessionLocal() as db:
        assert db.get(Prism, prism_id) is None
        assert BrainService.context(db) == ""
