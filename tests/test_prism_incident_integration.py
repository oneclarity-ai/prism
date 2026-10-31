from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.prism_v22 import (
    Prism,
    PrismExternalEvent,
    PrismIncident,
    PrismNotification,
    PrismObservation,
)
from app.schemas.prism_v22 import PrismCreate
from app.services.errors import RuleViolationError
from app.services.prism_incident_service import PrismIncidentService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.prism_notification_service import PrismNotificationService

T0 = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)


def _event(chat: str, message: str) -> PrismExternalEvent:
    return PrismExternalEvent(
        id=uuid.uuid4(),
        tenant_id="tenant",
        source_external_id=chat,
        external_message_id=message,
    )


def _observe(db, prism: Prism, event, now, signal="production_incident") -> PrismObservation:
    observation = PrismObservation(
        prism_id=prism.id,
        state="open",
        signal_type=signal,
        urgency="critical",
        confidence=0.9,
        summary=f"{prism.name} sees an incident.",
        verified_facts=[],
        why_it_matters="Impact.",
        suggested_next_step="Follow up.",
        unknowns=[],
        evidence_event_ids=[],
        source_external_id=event.source_external_id,
        fingerprint=uuid.uuid4().hex,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(observation)
    PrismIncidentService.assign(db, observation, event, now)
    db.commit()
    PrismNotificationService.record(db, [observation.id], now)
    return observation


def test_incident_grouping_evolution_and_split() -> None:
    marker = uuid.uuid4().hex[:8]
    chat = f"chat-{marker}"
    prism_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            first = PrismLifecycleService.create(
                db, PrismCreate(name=f"Exec {marker}", description="Executive.")
            )
            second = PrismLifecycleService.create(
                db, PrismCreate(name=f"Ops {marker}", description="Operations.")
            )
            prism_ids += [first.id, second.id]

            a = _observe(db, first, _event(chat, "m1"), T0)
            # A copied message seen by another Prism joins the same incident.
            b = _observe(db, second, _event(chat, "m1"), T0 + timedelta(minutes=1))
            assert a.incident_id == b.incident_id
            notes = {
                n.observation_id: n
                for n in db.query(PrismNotification).filter(
                    PrismNotification.observation_id.in_([a.id, b.id])
                )
            }
            assert notes[a.id].state == "pending"
            assert (notes[b.id].state, notes[b.id].result) == ("skipped", "duplicate_incident")
            assert db.get(PrismObservation, b.id).summary.startswith("Ops")  # own explanation kept

            # Same words, different message and chat: never merged by text.
            other = _observe(db, first, _event(f"other-{marker}", "m9"), T0 + timedelta(minutes=2))
            assert other.incident_id != a.incident_id

            # Same Prism, same chat, in window: an update on the same incident.
            c = _observe(db, first, _event(chat, "m2"), T0 + timedelta(hours=1))
            assert c.incident_id == a.incident_id
            # Resolution is an event, and the incident resolves only when none are open.
            for observation in (a, c):
                observation.state = "resolved"
                PrismIncidentService.on_resolved(db, observation, T0 + timedelta(hours=2))
            db.commit()
            assert db.get(PrismIncident, a.incident_id).state == "open"  # b still open
            b.state = "resolved"
            PrismIncidentService.on_resolved(db, b, T0 + timedelta(hours=3))
            db.commit()
            assert db.get(PrismIncident, a.incident_id).state == "resolved"

            # Recurrence reopens, and is alerted again.
            d = _observe(db, first, _event(chat, "m4"), T0 + timedelta(hours=4))
            assert d.incident_id == a.incident_id
            assert db.get(PrismIncident, a.incident_id).state == "open"
            assert (
                db.query(PrismNotification).filter_by(observation_id=d.id).one().state == "pending"
            )

            # Outside the window: a new incident.
            late = _observe(db, first, _event(chat, "m3"), T0 + timedelta(days=3))
            assert late.incident_id != a.incident_id

            history = PrismIncidentService.history(db, second.id, b.id)
            kinds = [event["event_type"] for event in history["events"]]
            assert {"opened", "linked", "resolved", "reopened"} <= set(kinds)
            assert history["other_prisms"] == 1
            for event in history["events"]:
                if not event["mine"]:
                    assert event["observation_id"] is None
                    assert first.name not in event["reason"]

            # Split a false grouping without deleting anything.
            PrismIncidentService.split(db, second.id, b.id, T0 + timedelta(hours=5))
            db.expire_all()
            assert db.get(PrismObservation, b.id).incident_id != a.incident_id
            assert db.get(PrismObservation, a.id) is not None
            with pytest.raises(RuleViolationError):
                PrismIncidentService.split(db, second.id, b.id, T0)
    finally:
        with SessionLocal() as db:
            for prism_id in prism_ids:
                db.execute(delete(Prism).where(Prism.id == prism_id))
            db.execute(
                delete(PrismIncident).where(
                    ~select(PrismObservation.id)
                    .where(PrismObservation.incident_id == PrismIncident.id)
                    .exists()
                )
            )
            db.commit()
