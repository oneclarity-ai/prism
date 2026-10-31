from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism, PrismNotification, PrismObservation, PrismPresence
from app.schemas.prism_v22 import PrismCreate, PrismNotificationSettingUpdate
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.prism_notification_service import PrismNotificationService


def _active_prism(db, name: str) -> Prism:
    prism = PrismLifecycleService.create(db, PrismCreate(name=name, description="Watches things."))
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


def _observation(db, prism: Prism, urgency: str = "critical") -> PrismObservation:
    now = datetime.now(timezone.utc)
    observation = PrismObservation(
        prism_id=prism.id,
        state="open",
        signal_type="production_incident",
        urgency=urgency,
        confidence=0.9,
        summary="Checkout is down.",
        verified_facts=["Asha: checkout is down"],
        why_it_matters="Customers cannot pay.",
        suggested_next_step="Ask for an owner.",
        unknowns=[],
        evidence_event_ids=[],
        source_external_id="chat-1",
        source_label="Engineering",
        fingerprint=uuid.uuid4().hex,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)
    return observation


def test_notification_is_claimed_once_and_never_leaks_evidence() -> None:
    marker = uuid.uuid4().hex[:8]
    client_a, client_b = f"tab-a-{marker}", f"tab-b-{marker}"
    prism_id: uuid.UUID | None = None
    try:
        with SessionLocal() as db:
            prism = _active_prism(db, f"Notify {marker}")
            prism_id = prism.id
            observation = _observation(db, prism)
            PrismNotificationService.record(db, [observation.id])
            PrismNotificationService.record(db, [observation.id])  # idempotent
            assert db.query(PrismNotification).filter_by(observation_id=observation.id).count() == 1

            summary = {s.prism_id: s for s in PrismNotificationService.update_summaries(db)}
            assert summary[prism.id].unread == 1 and summary[prism.id].urgent_unread == 1

            # No live page -> nothing claimed, update stays unread and monitoring is unaffected.
            assert PrismNotificationService.claim_next(db, client_a) is None

            # Opt-in is required before anything is attempted.
            PrismNotificationService.heartbeat(db, client_a)
            PrismNotificationService.heartbeat(db, client_b)
            assert PrismNotificationService.claim_next(db, client_a) is None
            row = db.query(PrismNotification).filter_by(observation_id=observation.id).one()
            assert (row.state, row.result) == ("skipped", "disabled")

            second = _observation(db, prism)
            PrismNotificationService.record(db, [second.id])
            PrismNotificationService.update_setting(
                db, prism.id, PrismNotificationSettingUpdate(enabled=True, min_urgency="high")
            )
            claim = PrismNotificationService.claim_next(db, client_a)
            assert claim is not None and claim.observation_id == second.id
            assert "Checkout" not in claim.body and "Asha" not in claim.body
            # A second tab cannot claim the same notification.
            assert PrismNotificationService.claim_next(db, client_b) is None
            # Only the claiming page can report, and only once.
            PrismNotificationService.report(db, claim.notification_id, client_b, "delivered")
            PrismNotificationService.report(db, claim.notification_id, client_a, "denied")
            PrismNotificationService.report(db, claim.notification_id, client_a, "delivered")
            db.expire_all()
            done = db.get(PrismNotification, claim.notification_id)
            assert (done.state, done.result) == ("failed", "denied")

            # Marking read and resolving close later attempts.
            low = _observation(db, prism, urgency="low")
            PrismNotificationService.record(db, [low.id])
            assert PrismNotificationService.claim_next(db, client_a) is None
            assert (
                db.query(PrismNotification).filter_by(observation_id=low.id).one().result
                == "below_threshold"
            )
            assert PrismNotificationService.mark_read(db, prism.id, [second.id]) == 1
            assert PrismNotificationService.mark_read(db, prism.id, [second.id]) == 0
    finally:
        with SessionLocal() as db:
            if prism_id:
                db.execute(delete(Prism).where(Prism.id == prism_id))
            db.execute(delete(PrismPresence).where(PrismPresence.client_id.like(f"%{marker}")))
            db.commit()
