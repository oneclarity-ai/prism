"""Retention for raw Teams events, preserving everything an action or incident still needs.

Observations keep their own verified facts, and proposals, approvals, and deliveries
never reference raw events, so action audit stays explainable after compaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.prisms.prism_v22 import (
    PrismExternalEvent,
    PrismNotification,
    PrismObservation,
    PrismObservationDraft,
    PrismPresence,
)

BATCH = 1000


class PrismRetentionService:
    @staticmethod
    def cutoff(now: datetime) -> datetime:
        settings = get_settings()
        # Never keep less than the signal lookback window plus a day.
        days = max(settings.v22_event_retention_days, settings.v22_signal_lookback_hours // 24 + 1)
        return now - timedelta(days=days)

    @classmethod
    def protected_event_ids(cls, db: Session) -> set[str]:
        """Evidence still needed: open observations and drafts that are still live."""

        protected: set[str] = set()
        for ids in db.scalars(
            select(PrismObservation.evidence_event_ids).where(PrismObservation.state == "open")
        ):
            protected.update(str(item) for item in ids or [])
        for ids in db.scalars(
            select(PrismObservationDraft.evidence_event_ids).where(
                PrismObservationDraft.invalidated_at.is_(None)
            )
        ):
            protected.update(str(item) for item in ids or [])
        return protected

    @classmethod
    def compact(cls, db: Session, now: datetime | None = None) -> dict[str, int]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = cls.cutoff(current)
        protected = cls.protected_event_ids(db)
        removed = 0
        while True:
            ids = list(
                db.scalars(
                    select(PrismExternalEvent.id)
                    .where(PrismExternalEvent.occurred_at < cutoff)
                    .order_by(PrismExternalEvent.occurred_at)
                    .limit(BATCH)
                )
            )
            doomed = [item for item in ids if str(item) not in protected]
            if doomed:
                db.execute(delete(PrismExternalEvent).where(PrismExternalEvent.id.in_(doomed)))
                db.commit()
                removed += len(doomed)
            if len(ids) < BATCH or not doomed:
                break
        # Closed delivery attempts older than the window carry no audit value.
        db.execute(
            delete(PrismNotification).where(
                PrismNotification.created_at < cutoff,
                PrismNotification.state.in_(("delivered", "skipped", "failed")),
            )
        )
        db.execute(
            delete(PrismPresence).where(PrismPresence.last_seen_at < current - timedelta(hours=1))
        )
        db.commit()
        return {"events_removed": removed}
