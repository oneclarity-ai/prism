from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.enums import PrismLifecycleState
from app.models.prisms.agent_v21 import AgentThread
from app.models.prisms.prism_v22 import Prism
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.prisms.agent_preference_service import AgentPreferenceService
from app.services.prisms.prism_conversation_service import PrismConversationService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService


def _activate(db, prism: Prism) -> Prism:
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
    return prism


def test_preferences_belong_to_one_prism_only(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    get_settings.cache_clear()
    created: list[uuid.UUID] = []
    try:
        client = TestClient(app)
        with SessionLocal() as db:
            first = PrismLifecycleService.create(
                db, PrismCreate(name=f"Pref A {uuid.uuid4().hex[:6]}", description="First.")
            )
            second = PrismLifecycleService.create(
                db, PrismCreate(name=f"Pref B {uuid.uuid4().hex[:6]}", description="Second.")
            )
            created += [first.id, second.id]
            first = _activate(db, first)
            _, thread = PrismConversationService.canonical_thread(db, first.id)
            thread_id = thread.id

        added = client.post(
            f"/api/v2/prisms/{first.id}/preferences", json={"instruction": "Keep it short"}
        )
        assert added.status_code == 201
        preference_id = added.json()["id"]

        listed_first = client.get(f"/api/v2/prisms/{first.id}/preferences").json()
        assert [item["id"] for item in listed_first] == [preference_id]
        assert client.get(f"/api/v2/prisms/{second.id}/preferences").json() == []
        # Neither the legacy list nor another Prism's drafts see it.
        assert preference_id not in {
            item["id"] for item in client.get("/api/v2/agent/preferences").json()
        }
        with SessionLocal() as db:
            assert [p.id for p in AgentPreferenceService.active(db, thread_id=thread_id)] == [
                uuid.UUID(preference_id)
            ]

        # Another Prism cannot change or remove it.
        other = f"/api/v2/prisms/{second.id}/preferences/{preference_id}"
        assert client.patch(other, json={"is_active": False}).status_code == 404
        assert client.delete(other).status_code == 404

        own = f"/api/v2/prisms/{first.id}/preferences/{preference_id}"
        paused = client.patch(own, json={"is_active": False}).json()
        assert paused["is_active"] is False and paused["instruction"] == "Keep it short"
        edited = client.patch(own, json={"instruction": "Keep it brief"}).json()
        assert edited["instruction"] == "Keep it brief" and edited["is_active"] is False
        with SessionLocal() as db:
            assert AgentPreferenceService.active(db, thread_id=thread_id) == []

        assert client.delete(own).status_code == 204
        assert client.get(f"/api/v2/prisms/{first.id}/preferences").json() == []
    finally:
        get_settings.cache_clear()
        with SessionLocal() as db:
            db.execute(delete(AgentThread).where(AgentThread.prism_id.in_(created)))
            db.execute(delete(Prism).where(Prism.id.in_(created)))
            db.commit()
