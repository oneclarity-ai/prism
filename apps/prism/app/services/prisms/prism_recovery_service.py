"""Operator recovery for stuck v2.2 work. Nothing here reads Teams or sends anything."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.prisms.prism_v22 import PrismNotification, PrismRun, PrismTeamsSourceCursor
from app.services.prisms.prism_run_service import PrismRunService


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrismRecoveryService:
    @staticmethod
    def status(db: Session, now: datetime | None = None) -> dict[str, int]:
        current = now or _now()

        def count(model, *conditions) -> int:
            return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)

        return {
            "runs_queued": count(PrismRun, PrismRun.state == "queued"),
            "runs_running": count(PrismRun, PrismRun.state == "running"),
            "runs_lease_expired": count(
                PrismRun, PrismRun.state == "running", PrismRun.lease_expires_at < current
            ),
            "notifications_pending": count(PrismNotification, PrismNotification.state == "pending"),
            "notifications_claimed": count(PrismNotification, PrismNotification.state == "claimed"),
            "cursors_degraded": count(
                PrismTeamsSourceCursor, PrismTeamsSourceCursor.status == "degraded"
            ),
        }

    @staticmethod
    def recover_runs(
        db: Session,
        *,
        now: datetime | None = None,
        cancel_queued_older_than_minutes: int | None = None,
        force_running: bool = False,
    ) -> dict[str, int]:
        current = now or _now()
        recovered = PrismRunService.recover_expired_leases(db, now=current)
        forced = cancelled = 0
        if force_running:
            forced = db.execute(
                update(PrismRun)
                .where(PrismRun.state == "running")
                .values(
                    state="failed",
                    safe_error="Stopped by an operator recovery command.",
                    completed_at=current,
                    lease_expires_at=None,
                    lease_owner=None,
                )
            ).rowcount
        if cancel_queued_older_than_minutes is not None:
            cancelled = db.execute(
                update(PrismRun)
                .where(
                    PrismRun.state == "queued",
                    PrismRun.created_at
                    < current - timedelta(minutes=cancel_queued_older_than_minutes),
                )
                .values(
                    state="cancelled",
                    safe_error="Cancelled by an operator recovery command.",
                    completed_at=current,
                )
            ).rowcount
        db.commit()
        return {
            "leases_recovered": recovered,
            "forced_failed": int(forced),
            "queued_cancelled": int(cancelled),
        }

    @staticmethod
    def recover_notifications(
        db: Session, *, now: datetime | None = None, stale_minutes: int = 5
    ) -> int:
        """A claim whose page vanished never reported; close it so it cannot linger forever."""

        current = now or _now()
        closed = db.execute(
            update(PrismNotification)
            .where(
                PrismNotification.state == "claimed",
                PrismNotification.claimed_at < current - timedelta(minutes=stale_minutes),
            )
            .values(state="failed", result="no_result", completed_at=current)
        ).rowcount
        db.commit()
        return int(closed)

    @staticmethod
    def reset_cursors(db: Session, prism_id: uuid.UUID | None = None) -> int:
        statement = (
            update(PrismTeamsSourceCursor)
            .where(PrismTeamsSourceCursor.status == "degraded")
            .values(status="idle", last_error=None)
        )
        if prism_id is not None:
            statement = statement.where(PrismTeamsSourceCursor.prism_id == prism_id)
        count = db.execute(statement).rowcount
        db.commit()
        return int(count)
