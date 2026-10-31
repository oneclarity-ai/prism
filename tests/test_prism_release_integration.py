"""Release-gate checks: migration, rollback, recovery, isolation, auth, and restart safety."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.agent_v21 import AgentThread
from app.models.enums import PrismLifecycleState, PrismOnboardingStatus
from app.models.prism_v22 import (
    Prism,
    PrismExternalEvent,
    PrismIncident,
    PrismNotification,
    PrismObservation,
    PrismOnboardingSession,
    PrismRun,
    PrismWorkingAgreement,
)
from app.schemas.prism_v22 import PrismCreate
from app.services.agent_state_service import AgentStateService
from app.services.prism_health_service import PrismHealthService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.prism_migration_service import PrismMigrationService
from app.services.prism_notification_service import PrismNotificationService
from app.services.prism_observation_service import PrismObservationService
from app.services.prism_recovery_service import PrismRecoveryService
from app.services.prism_run_service import PrismRunService

SIGNALS = ["Production incidents"]


def _activate(db, name: str) -> Prism:
    prism = PrismLifecycleService.create(db, PrismCreate(name=name, description="Watches things."))
    session = PrismOnboardingSession(prism_id=prism.id, status=PrismOnboardingStatus.COMPLETED)
    db.add(session)
    db.flush()
    db.add(
        PrismWorkingAgreement(
            prism_id=prism.id,
            onboarding_session_id=session.id,
            revision=1,
            status="confirmed",
            template_key=prism.template_key,
            agreement={"attention_signals": SIGNALS},
            confirmed_at=datetime.now(timezone.utc),
        )
    )
    prism.agreement_revision = 1
    db.commit()
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


def _cleanup(prism_ids: list[uuid.UUID]) -> None:
    with SessionLocal() as db:
        db.execute(delete(AgentThread).where(AgentThread.prism_id.in_(prism_ids)))
        db.execute(delete(Prism).where(Prism.id.in_(prism_ids)))
        db.execute(
            delete(PrismIncident).where(
                ~select(PrismObservation.id)
                .where(PrismObservation.incident_id == PrismIncident.id)
                .exists()
            )
        )
        db.commit()


def _client(monkeypatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return TestClient(app)


def test_cross_prism_ids_are_refused_and_everything_needs_the_operator_token(monkeypatch) -> None:
    marker = uuid.uuid4().hex[:8]
    ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            a, b = _activate(db, f"A {marker}"), _activate(db, f"B {marker}")
            ids += [a.id, b.id]
            now = datetime.now(timezone.utc)
            observation = PrismObservation(
                prism_id=a.id,
                state="open",
                signal_type="blocker",
                urgency="low",
                confidence=0.5,
                summary="s",
                verified_facts=[],
                why_it_matters="w",
                suggested_next_step="n",
                unknowns=[],
                evidence_event_ids=[],
                source_external_id="c",
                fingerprint=uuid.uuid4().hex,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(observation)
            db.commit()
            observation_id = observation.id

        client = _client(monkeypatch, PRISM_V22_ENABLED="true", PRISM_V21_ENABLED="true")
        foreign = f"/api/v2/prisms/{b.id}/observations/{observation_id}"
        for method, path, body in (
            ("get", f"{foreign}/incident", None),
            ("post", f"{foreign}/incident/split", None),
            ("post", f"{foreign}/feedback", {"kind": "helpful"}),
            ("get", f"{foreign}/drafts", None),
            ("post", f"{foreign}/drafts", {"request_id": str(uuid.uuid4())}),
        ):
            response = getattr(client, method)(path, **({"json": body} if body else {}))
            assert response.status_code == 404, (path, response.status_code)

        # Every v2.2 route is behind the operator token once one is configured.
        guarded = _client(monkeypatch, OPERATOR_API_TOKEN="release-gate-token")
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/v2/prisms"):
                continue
            url = path.replace("{prism_id}", str(a.id)).replace(
                "{observation_id}", str(observation_id)
            )
            url = url.replace("{notification_id}", str(uuid.uuid4())).replace(
                "{signal_type}", "blocker"
            )
            for method in route.methods - {"HEAD", "OPTIONS"}:
                response = guarded.request(method, url, json={})
                assert response.status_code == 401, (method, path)
                assert response.json()["code"] == "operator_auth_required"
        monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    finally:
        get_settings.cache_clear()
        _cleanup(ids)


def test_turning_v22_off_leaves_v21_usable_and_v22_records_intact(monkeypatch) -> None:
    marker = uuid.uuid4().hex[:8]
    ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            prism = _activate(db, f"Rollback {marker}")
            ids.append(prism.id)
        off = _client(monkeypatch, PRISM_V22_ENABLED="false", PRISM_V21_ENABLED="true")
        assert off.get("/api/v2/prisms").status_code == 404
        assert off.get(f"/api/v2/prisms/{prism.id}/health").status_code == 404
        assert off.get("/api/v2/agent/conversation").status_code == 200
        with SessionLocal() as db:
            assert db.get(Prism, prism.id) is not None  # nothing destroyed
    finally:
        get_settings.cache_clear()
        _cleanup(ids)


def test_v21_conversation_migrates_without_losing_anything_and_needs_review() -> None:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        legacy = PrismMigrationService.legacy_thread(db)
        if legacy is None:
            legacy = AgentStateService.canonical_thread(db)
        legacy_id = legacy.id
        result = PrismMigrationService.adopt_legacy_conversation(db)
        assert result["status"] == "migrated"
        prism = db.get(Prism, uuid.UUID(result["prism_id"]))
        db.refresh(legacy)
        assert (
            prism.state == PrismLifecycleState.ACTIVE
            and prism.template_key == "executive_assistant"
        )
        assert legacy.id == legacy_id and legacy.prism_id == prism.id  # same thread, new owner
        assert PrismMigrationService.adopt_legacy_conversation(db)["status"] == "nothing_to_migrate"
        # v2.1 still resolves the same conversation, so rollback never forks history.
        assert AgentStateService.canonical_thread(db).id == legacy_id

        # Manual-only, and no automatic run until the user reviews.
        assert PrismRunService.get_policy(db, prism.id).mode == "manual"
        assert PrismHealthService.review_required(db, prism.id)
        reason = PrismHealthService.block_reason(
            db, prism.id, "continuous", datetime.now(timezone.utc)
        )
        assert reason and "review this migrated Prism" in reason
        assert (
            PrismHealthService.block_reason(db, prism.id, "manual", datetime.now(timezone.utc))
            is None
        )
        PrismMigrationService.acknowledge_review(db, prism.id)
        assert not PrismHealthService.review_required(db, prism.id)
    finally:
        db.close()
        outer.rollback()
        connection.close()


def test_recovery_commands_unstick_runs_notifications_and_cursors() -> None:
    marker = uuid.uuid4().hex[:8]
    ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            prism = _activate(db, f"Recover {marker}")
            ids.append(prism.id)
            policy = PrismRunService.get_policy(db, prism.id)
            now = datetime.now(timezone.utc)

            def run(state: str, **fields) -> PrismRun:
                item = PrismRun(
                    prism_id=prism.id,
                    trigger_policy_id=policy.id,
                    trigger_type="continuous",
                    occurrence_key=uuid.uuid4().hex,
                    state=state,
                    **fields,
                )
                db.add(item)
                db.commit()
                return item

            stuck = run(
                "running",
                started_at=now - timedelta(hours=1),
                lease_expires_at=now - timedelta(minutes=30),
                attempt_count=1,
            )
            old_queued = run("queued")
            old_queued.created_at = now - timedelta(hours=3)
            db.commit()
            result = PrismRecoveryService.recover_runs(db, cancel_queued_older_than_minutes=60)
            assert result["leases_recovered"] >= 1 and result["queued_cancelled"] >= 1
            db.expire_all()
            assert db.get(PrismRun, stuck.id).state == "queued"
            assert db.get(PrismRun, old_queued.id).state == "cancelled"

            observation = PrismObservation(
                prism_id=prism.id,
                state="open",
                signal_type="blocker",
                urgency="high",
                confidence=0.5,
                summary="s",
                verified_facts=[],
                why_it_matters="w",
                suggested_next_step="n",
                unknowns=[],
                evidence_event_ids=[],
                source_external_id="c",
                fingerprint=uuid.uuid4().hex,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(observation)
            db.flush()
            claim = PrismNotification(
                prism_id=prism.id,
                observation_id=observation.id,
                state="claimed",
                claimed_by="tab",
                claimed_at=now - timedelta(minutes=30),
            )
            db.add(claim)
            db.commit()
            assert PrismRecoveryService.recover_notifications(db) >= 1
            db.expire_all()
            assert (
                db.get(PrismNotification, claim.id).state,
                db.get(PrismNotification, claim.id).result,
            ) == ("failed", "no_result")
    finally:
        _cleanup(ids)


def test_duplicate_incident_alerts_once_and_survives_restart_and_pause() -> None:
    marker = uuid.uuid4().hex[:8]
    chat = f"chat-{marker}"
    ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            exec_prism, qa = _activate(db, f"Exec {marker}"), _activate(db, f"QA {marker}")
            ids += [exec_prism.id, qa.id]
            now = datetime.now(timezone.utc)
            for prism in (exec_prism, qa):
                policy = PrismRunService.get_policy(db, prism.id)
                db.add(
                    PrismExternalEvent(
                        prism_id=prism.id,
                        tenant_id="t",
                        microsoft_user_id="u",
                        source_external_id=chat,
                        source_label="Engineering",
                        external_message_id="m1",
                        event_kind="created",
                        source_version="1",
                        dedupe_key=uuid.uuid4().hex,
                        occurred_at=now - timedelta(minutes=5),
                        sender_display_name="Asha",
                        body_text="Prod is down, checkout returning 500s",
                        event_metadata={},
                    )
                )
                run = PrismRun(
                    prism_id=prism.id,
                    trigger_policy_id=policy.id,
                    trigger_type="manual",
                    occurrence_key=uuid.uuid4().hex,
                    state="running",
                )
                db.add(run)
                db.commit()
                outcome = PrismObservationService.evaluate_run(
                    db, prism_id=prism.id, run_id=run.id, now=now
                )
                assert outcome["created"] == 1

        # "Restart": brand-new sessions see the same durable state.
        with SessionLocal() as db:
            observations = list(
                db.query(PrismObservation).filter(PrismObservation.prism_id.in_(ids))
            )
            assert len(observations) == 2
            assert len({o.incident_id for o in observations}) == 1  # one incident, two Prisms
            assert {o.prism_id for o in observations} == set(ids)  # each keeps its own record
            states = sorted(
                n.state
                for n in db.query(PrismNotification).filter(PrismNotification.prism_id.in_(ids))
            )
            assert states == ["pending", "skipped"]  # one browser alert, not two
            # Re-evaluating after a restart creates nothing new.
            run = PrismRun(
                prism_id=qa.id,
                trigger_policy_id=PrismRunService.get_policy(db, qa.id).id,
                trigger_type="manual",
                occurrence_key=uuid.uuid4().hex,
                state="running",
            )
            db.add(run)
            db.commit()
            again = PrismObservationService.evaluate_run(
                db, prism_id=qa.id, run_id=run.id, now=datetime.now(timezone.utc)
            )
            assert again["created"] == 0

            # Pause QA: its queued automatic run is skipped, never executed.
            policy = PrismRunService.get_policy(db, qa.id)
            queued = PrismRun(
                prism_id=qa.id,
                trigger_policy_id=policy.id,
                trigger_type="continuous",
                occurrence_key=uuid.uuid4().hex,
                state="queued",
            )
            db.add(queued)
            db.commit()
            PrismLifecycleService.transition(
                db,
                qa.id,
                target=PrismLifecycleState.PAUSED,
                expected_lifecycle_version=db.get(Prism, qa.id).lifecycle_version,
                event_type="paused",
            )
            assert PrismRunService._claim(db, queued.id, datetime.now(timezone.utc)) is None
            db.expire_all()
            assert db.get(PrismRun, queued.id).state == "skipped"
        PrismNotificationService  # imported for clarity of the alert path under test
    finally:
        _cleanup(ids)
