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
from app.models.agent_v21 import AgentThread
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism, PrismLifecycleEvent
from app.schemas.prism_v22 import PrismCreate
from app.services.errors import ConflictError, RuleViolationError
from app.services.prism_lifecycle_service import PrismLifecycleService


def _cleanup(prism_ids: list[uuid.UUID], thread_ids: list[uuid.UUID]) -> None:
    with SessionLocal() as db:
        if thread_ids:
            db.execute(delete(AgentThread).where(AgentThread.id.in_(thread_ids)))
        if prism_ids:
            db.execute(delete(Prism).where(Prism.id.in_(prism_ids)))
        db.commit()


def test_prisms_keep_names_lifecycles_and_canonical_threads_isolated() -> None:
    prism_ids: list[uuid.UUID] = []
    thread_ids: list[uuid.UUID] = []
    marker = uuid.uuid4().hex[:8]
    try:
        with SessionLocal() as db:
            executive = PrismLifecycleService.create(
                db,
                PrismCreate(
                    name=f"Executive Assistant {marker}",
                    description="Keep the manager updated.",
                    template_key="executive_assistant",
                    template_version="1",
                ),
            )
            qa = PrismLifecycleService.create(
                db,
                PrismCreate(name=f"QA Prism {marker}", description="Watch QA readiness."),
            )
            prism_ids.extend([executive.id, qa.id])

            with pytest.raises(ConflictError):
                PrismLifecycleService.create(
                    db,
                    PrismCreate(
                        name=f"  executive  assistant {marker.upper()} ",
                        description="Duplicate active name.",
                    ),
                )
            db.rollback()

            executive = PrismLifecycleService.transition(
                db,
                executive.id,
                target=PrismLifecycleState.ONBOARDING,
                expected_lifecycle_version=executive.lifecycle_version,
                event_type="onboarding_started",
            )
            executive = PrismLifecycleService.transition(
                db,
                executive.id,
                target=PrismLifecycleState.AWAITING_CONFIRMATION,
                expected_lifecycle_version=executive.lifecycle_version,
                event_type="agreement_prepared",
            )
            with pytest.raises(RuleViolationError):
                PrismLifecycleService.transition(
                    db,
                    executive.id,
                    target=PrismLifecycleState.ACTIVE,
                    expected_lifecycle_version=executive.lifecycle_version,
                    event_type="activation_requested",
                )
            db.rollback()
            executive = PrismLifecycleService.transition(
                db,
                executive.id,
                target=PrismLifecycleState.ACTIVE,
                expected_lifecycle_version=executive.lifecycle_version,
                event_type="agreement_confirmed",
                agreement_confirmed=True,
            )

            first_thread = AgentThread(
                title="Executive conversation",
                prism_id=executive.id,
                is_canonical=True,
                source_metadata={},
            )
            second_thread = AgentThread(
                title="QA conversation",
                prism_id=qa.id,
                is_canonical=True,
                source_metadata={},
            )
            db.add_all([first_thread, second_thread])
            db.commit()
            thread_ids.extend([first_thread.id, second_thread.id])

            executive = PrismLifecycleService.transition(
                db,
                executive.id,
                target=PrismLifecycleState.ARCHIVED,
                expected_lifecycle_version=executive.lifecycle_version,
                event_type="archived",
            )
            events = PrismLifecycleService.events(db, executive.id)
            assert [event.target_state for event in events] == [
                PrismLifecycleState.DRAFT,
                PrismLifecycleState.ONBOARDING,
                PrismLifecycleState.AWAITING_CONFIRMATION,
                PrismLifecycleState.ACTIVE,
                PrismLifecycleState.ARCHIVED,
            ]

            reused = PrismLifecycleService.create(
                db,
                PrismCreate(
                    name=f"Executive Assistant {marker}",
                    description="A separate new draft may reuse an archived name.",
                ),
            )
            prism_ids.append(reused.id)
            assert reused.state == PrismLifecycleState.DRAFT
    finally:
        _cleanup(prism_ids, thread_ids)


def test_prism_api_creates_edits_and_archives_drafts(monkeypatch) -> None:
    marker = uuid.uuid4().hex[:8]
    prism_id: uuid.UUID | None = None
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v2/prisms",
            json={
                "name": f"Daily Brief {marker}",
                "description": "Summarize the day.",
                "template_key": "blank",
            },
        )
        assert created.status_code == 201
        payload = created.json()
        prism_id = uuid.UUID(payload["id"])
        assert payload["state"] == "draft"
        assert payload["lifecycle_version"] == 1

        updated = client.patch(
            f"/api/v2/prisms/{prism_id}",
            json={
                "expected_lifecycle_version": 1,
                "name": f"Daily Evening Brief {marker}",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["lifecycle_version"] == 2

        stale = client.patch(
            f"/api/v2/prisms/{prism_id}",
            json={"expected_lifecycle_version": 1, "description": "Stale browser update."},
        )
        assert stale.status_code == 409

        archived = client.post(
            f"/api/v2/prisms/{prism_id}/archive",
            json={"expected_lifecycle_version": 2, "reason": "Not needed yet."},
        )
        assert archived.status_code == 200
        assert archived.json()["state"] == "archived"
        visible_ids = {item["id"] for item in client.get("/api/v2/prisms").json()}
        assert str(prism_id) not in visible_ids
        all_ids = {item["id"] for item in client.get("/api/v2/prisms?include_archived=true").json()}
        assert str(prism_id) in all_ids
    finally:
        get_settings.cache_clear()
        if prism_id is not None:
            _cleanup([prism_id], [])


def test_prism_lifecycle_event_rows_are_registered() -> None:
    assert PrismLifecycleEvent.__tablename__ == "prism_lifecycle_events"
