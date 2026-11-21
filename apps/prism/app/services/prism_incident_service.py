"""Conservative incident links across Prism observations.

Grouping is deterministic: an exact Teams message plus signal class (any Prism),
or the same chat and signal class inside a bounded window (same Prism only).
Text similarity is never used. A link shares no memory or instructions; each
Prism keeps its own observation and recommendation.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.prism_v22 import (
    PrismExternalEvent,
    PrismIncident,
    PrismIncidentEvent,
    PrismObservation,
)
from app.services.errors import NotFoundError, RuleViolationError

OTHER_PRISM_REASON = "Another Prism observed the same event."


def _lock(db: Session, key: str) -> None:
    """Serialize concurrent workers on one evidence key or incident (released at commit)."""

    db.execute(
        select(func.pg_advisory_xact_lock(int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)))
    )


class PrismIncidentService:
    @staticmethod
    def evidence_key(signal_type: str, event: PrismExternalEvent) -> str:
        raw = f"v1:{signal_type}:{event.tenant_id}:{event.source_external_id}:{event.external_message_id}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _log(
        db: Session,
        incident: PrismIncident,
        observation: PrismObservation | None,
        event_type: str,
        reason: str,
        now: datetime,
    ) -> None:
        db.add(
            PrismIncidentEvent(
                incident_id=incident.id,
                observation_id=observation.id if observation else None,
                prism_id=observation.prism_id if observation else None,
                event_type=event_type,
                reason=reason,
                created_at=now,
            )
        )

    @classmethod
    def assign(
        cls, db: Session, observation: PrismObservation, event: PrismExternalEvent, now: datetime
    ) -> PrismIncident:
        """Attach a newly created observation to an incident, recording why."""

        db.flush()
        key = cls.evidence_key(observation.signal_type, event)
        observation.evidence_key = key
        _lock(db, key)
        window = timedelta(hours=get_settings().v22_incident_window_hours)

        incident = db.scalar(
            select(PrismIncident)
            .join(PrismObservation, PrismObservation.incident_id == PrismIncident.id)
            .where(PrismObservation.evidence_key == key, PrismObservation.id != observation.id)
            .order_by(PrismObservation.created_at)
            .limit(1)
        )
        reason = "Same Teams message and signal class as an earlier observation."
        kind = "linked"
        if incident is None:
            incident = db.scalar(
                select(PrismIncident)
                .join(PrismObservation, PrismObservation.incident_id == PrismIncident.id)
                .where(
                    PrismObservation.prism_id == observation.prism_id,
                    PrismObservation.source_external_id == observation.source_external_id,
                    PrismObservation.signal_type == observation.signal_type,
                    PrismObservation.id != observation.id,
                    PrismIncident.last_activity_at >= now - window,
                )
                .order_by(PrismIncident.last_activity_at.desc())
                .limit(1)
            )
            reason = (
                f"Same chat and signal class within {get_settings().v22_incident_window_hours} "
                "hours for this Prism."
            )
            kind = "updated"
        if incident is None:
            incident = PrismIncident(
                signal_type=observation.signal_type,
                state="open",
                opened_at=now,
                last_activity_at=now,
            )
            db.add(incident)
            db.flush()
            observation.incident_id = incident.id
            cls._log(db, incident, observation, "opened", "First observation of this signal.", now)
            return incident

        observation.incident_id = incident.id
        incident.last_activity_at = now
        if incident.state == "resolved":
            incident.state = "open"
            incident.resolved_at = None
            kind, reason = "reopened", "New matching evidence arrived after the incident resolved."
        cls._log(db, incident, observation, kind, reason, now)
        return incident

    @classmethod
    def on_resolved(cls, db: Session, observation: PrismObservation, now: datetime) -> None:
        """Record a resolution; the incident resolves only when no linked observation is open."""

        if observation.incident_id is None:
            return
        incident = db.get(PrismIncident, observation.incident_id)
        if incident is None:
            return
        _lock(db, str(incident.id))
        db.flush()
        cls._log(
            db, incident, observation, "resolved", "Resolution wording appeared in Teams.", now
        )
        still_open = db.scalar(
            select(func.count(PrismObservation.id)).where(
                PrismObservation.incident_id == incident.id, PrismObservation.state == "open"
            )
        )
        if not still_open and incident.state == "open":
            incident.state = "resolved"
            incident.resolved_at = now
        incident.last_activity_at = now

    @classmethod
    def split(
        cls, db: Session, prism_id: uuid.UUID, observation_id: uuid.UUID, now: datetime
    ) -> PrismIncident:
        """Undo a false grouping for one observation; nothing is deleted."""

        observation = db.get(PrismObservation, observation_id)
        if observation is None or observation.prism_id != prism_id:
            raise NotFoundError("Observation not found")
        if observation.incident_id is None:
            raise RuleViolationError("This observation is not linked to an incident")
        old = db.get(PrismIncident, observation.incident_id)
        _lock(db, str(old.id))
        linked = db.scalar(
            select(func.count(PrismObservation.id)).where(PrismObservation.incident_id == old.id)
        )
        if linked < 2:
            raise RuleViolationError("This observation is already its own incident")
        incident = PrismIncident(
            signal_type=observation.signal_type,
            state="resolved" if observation.state == "resolved" else "open",
            opened_at=observation.first_seen_at,
            last_activity_at=now,
        )
        db.add(incident)
        db.flush()
        cls._log(db, old, observation, "split", "You marked this as a different incident.", now)
        observation.incident_id = incident.id
        # A unique key keeps later matching evidence from silently regrouping it.
        observation.evidence_key = hashlib.sha256(f"split:{observation.id}".encode()).hexdigest()
        cls._log(db, incident, observation, "opened", "Split from a false grouping.", now)
        db.commit()
        return incident

    @classmethod
    def history(cls, db: Session, prism_id: uuid.UUID, observation_id: uuid.UUID) -> dict:
        observation = db.get(PrismObservation, observation_id)
        if observation is None or observation.prism_id != prism_id:
            raise NotFoundError("Observation not found")
        if observation.incident_id is None:
            return {"incident_id": None, "state": None, "other_prisms": 0, "events": []}
        incident = db.get(PrismIncident, observation.incident_id)
        others = db.scalar(
            select(func.count(func.distinct(PrismObservation.prism_id))).where(
                PrismObservation.incident_id == incident.id, PrismObservation.prism_id != prism_id
            )
        )
        events = db.scalars(
            select(PrismIncidentEvent)
            .where(PrismIncidentEvent.incident_id == incident.id)
            .order_by(PrismIncidentEvent.created_at, PrismIncidentEvent.id)
        )
        # Other Prisms' activity is shown without identity, wording, or evidence.
        return {
            "incident_id": incident.id,
            "state": incident.state,
            "other_prisms": int(others or 0),
            "events": [
                {
                    "event_type": event.event_type,
                    "reason": event.reason
                    if event.prism_id in (None, prism_id)
                    else OTHER_PRISM_REASON,
                    "created_at": event.created_at,
                    "mine": event.prism_id == prism_id,
                    "observation_id": event.observation_id if event.prism_id == prism_id else None,
                }
                for event in events
            ],
        }
