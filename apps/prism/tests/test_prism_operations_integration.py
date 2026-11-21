from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import PrismLifecycleState
from app.models.prisms.prism_v22 import (
    Prism,
    PrismExternalEvent,
    PrismObservation,
    PrismRun,
)
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.errors import RuleViolationError
from app.services.prisms.prism_health_service import PrismHealthService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.prisms.prism_retention_service import PrismRetentionService
from app.services.prisms.prism_run_service import PrismRunService
from app.services.prisms.prism_tuning_service import PrismTuningService

NOW = datetime.now(timezone.utc)


def _prism(db, name: str) -> Prism:
    prism = PrismLifecycleService.create(db, PrismCreate(name=name, description="Watches."))
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


def _observation(db, prism: Prism, signal="blocker", state="open", evidence=None):
    observation = PrismObservation(
        prism_id=prism.id,
        state=state,
        signal_type=signal,
        urgency="medium",
        confidence=0.8,
        summary="Secret body text.",
        verified_facts=["Asha: secret body text"],
        why_it_matters="Impact.",
        suggested_next_step="Follow up.",
        unknowns=[],
        evidence_event_ids=evidence or [],
        source_external_id="chat",
        fingerprint=uuid.uuid4().hex,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db.add(observation)
    db.commit()
    return observation


def _run(db, prism, policy, state, ago_minutes=0, trigger="continuous"):
    stamp = NOW - timedelta(minutes=ago_minutes)
    db.add(
        PrismRun(
            prism_id=prism.id,
            trigger_policy_id=policy.id,
            trigger_type=trigger,
            occurrence_key=uuid.uuid4().hex,
            state=state,
            started_at=stamp,
            completed_at=stamp,
            result={"metrics": {"model_calls": 2, "duration_ms": 10}},
        )
    )
    db.commit()


def test_feedback_tuning_is_prism_scoped_confirmed_and_safe() -> None:
    marker = uuid.uuid4().hex[:8]
    ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            first, second = _prism(db, f"A {marker}"), _prism(db, f"B {marker}")
            ids += [first.id, second.id]
            observations = [_observation(db, first) for _ in range(3)]
            for observation in observations:
                PrismTuningService.record_feedback(db, first.id, observation.id, "not_helpful")
            # Conflicting feedback on one observation: the latest wins.
            kinds = PrismTuningService.record_feedback(db, first.id, observations[0].id, "helpful")
            assert "not_helpful" not in kinds and "helpful" in kinds
            blocker = next(
                s for s in PrismTuningService.tuning(db, first.id) if s["signal_type"] == "blocker"
            )
            assert blocker["suggestion"] is None  # one helpful vote blocks the suggestion
            PrismTuningService.record_feedback(db, first.id, observations[0].id, "not_helpful")
            blocker = next(
                s for s in PrismTuningService.tuning(db, first.id) if s["signal_type"] == "blocker"
            )
            assert blocker["suggestion"] and not blocker["muted"]  # suggested, never applied
            assert PrismTuningService.muted_signals(db, first.id) == set()

            # Other Prisms are unaffected, and a foreign observation is refused.
            other = next(
                s for s in PrismTuningService.tuning(db, second.id) if s["signal_type"] == "blocker"
            )
            assert other["feedback"] == {} and other["suggestion"] is None
            with pytest.raises(Exception):
                PrismTuningService.record_feedback(db, second.id, observations[0].id, "helpful")

            # Only explicit confirmation mutes; mandatory safety signals can't be muted.
            PrismTuningService.set_muted(db, first.id, "blocker", True)
            assert PrismTuningService.muted_signals(db, first.id) == {"blocker"}
            assert PrismTuningService.muted_signals(db, second.id) == set()
            with pytest.raises(RuleViolationError):
                PrismTuningService.set_muted(db, first.id, "production_incident", True)
    finally:
        with SessionLocal() as db:
            db.execute(delete(Prism).where(Prism.id.in_(ids)))
            db.commit()


def test_budgets_circuit_breaker_health_and_no_leaks() -> None:
    marker = uuid.uuid4().hex[:8]
    prism_id = None
    try:
        with SessionLocal() as db:
            prism = _prism(db, f"Budget {marker}")
            prism_id = prism.id
            policy = PrismRunService.get_policy(db, prism.id)
            assert PrismHealthService.block_reason(db, prism.id, "continuous", NOW) is None

            PrismTuningService.update_budget(
                db, prism.id, {"max_runs_per_day": 2, "max_consecutive_failures": 2}
            )
            _run(db, prism, policy, "completed", 30)
            _run(db, prism, policy, "completed", 20)
            assert "daily run budget" in PrismHealthService.block_reason(
                db, prism.id, "continuous", NOW
            )
            assert PrismHealthService.block_reason(db, prism.id, "manual", NOW) is None

            # Recovery at the next window.
            tomorrow = NOW + timedelta(days=1, minutes=1)
            assert PrismHealthService.runs_today(db, prism.id, tomorrow) == 0

            PrismTuningService.update_budget(db, prism.id, {"max_runs_per_day": 100})
            _run(db, prism, policy, "failed", 5)
            _run(db, prism, policy, "failed", 1)
            assert "paused after 2 failed" in PrismHealthService.block_reason(
                db, prism.id, "continuous", NOW
            )
            assert PrismHealthService.block_reason(db, prism.id, "manual", NOW) is None
            # Backoff elapses, so it retries.
            assert (
                PrismHealthService.block_reason(
                    db, prism.id, "continuous", NOW + timedelta(hours=2)
                )
                is None
            )

            _observation(db, prism)
            status = PrismHealthService.status(db, prism.id)
            blob = json.dumps(status, default=str)
            assert "secret body text" not in blob.lower()
            assert status["monitoring"]["consecutive_failures"] == 2
            assert status["budget"]["model_calls_today"] == 8
            assert any("failed" in line for line in status["diagnosis"])
    finally:
        with SessionLocal() as db:
            if prism_id:
                db.execute(delete(Prism).where(Prism.id == prism_id))
                db.commit()


def test_retention_removes_old_events_but_keeps_needed_evidence() -> None:
    marker = uuid.uuid4().hex[:8]
    prism_id = None
    try:
        with SessionLocal() as db:
            prism = _prism(db, f"Retain {marker}")
            prism_id = prism.id
            old = NOW - timedelta(days=90)

            def event(message: str, when: datetime) -> PrismExternalEvent:
                item = PrismExternalEvent(
                    prism_id=prism.id,
                    tenant_id="t",
                    microsoft_user_id="u",
                    source_external_id=f"chat-{marker}",
                    external_message_id=message,
                    event_kind="created",
                    source_version=message,
                    dedupe_key=uuid.uuid4().hex,
                    occurred_at=when,
                    sender_display_name="Asha",
                    body_text="text",
                    event_metadata={},
                )
                db.add(item)
                db.flush()
                return item

            expired, kept_for_incident, recent = (
                event("old", old),
                event("old-open", old),
                event("new", NOW),
            )
            _observation(db, prism, evidence=[str(kept_for_incident.id)])
            db.commit()
            ids = (expired.id, kept_for_incident.id, recent.id)

            result = PrismRetentionService.compact(db, NOW)
            assert result["events_removed"] >= 1
            db.expire_all()
            assert db.get(PrismExternalEvent, ids[0]) is None  # eligible raw data gone
            assert db.get(PrismExternalEvent, ids[1]) is not None  # open incident evidence kept
            assert db.get(PrismExternalEvent, ids[2]) is not None  # inside the window kept
    finally:
        with SessionLocal() as db:
            if prism_id:
                db.execute(delete(Prism).where(Prism.id == prism_id))
                db.commit()
