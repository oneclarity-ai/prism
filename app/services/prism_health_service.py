"""Run guards, health, and metrics for a Prism. Metrics are counts only, never message text."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.microsoft_connection import MicrosoftConnection
from app.models.prism_v22 import (
    PrismExternalEvent,
    PrismNotification,
    PrismObservation,
    PrismObservationDraft,
    PrismObservationFeedback,
    PrismRun,
    PrismTeamsSourceCursor,
    PrismTriggerPolicy,
    PrismWorkingAgreement,
)
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.prism_tuning_service import PrismTuningService

COUNTED_STATES = ("running", "completed", "failed")


def _day_start(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


class PrismHealthService:
    @staticmethod
    def runs_today(db: Session, prism_id: uuid.UUID, now: datetime) -> int:
        return int(
            db.scalar(
                select(func.count(PrismRun.id)).where(
                    PrismRun.prism_id == prism_id,
                    PrismRun.started_at >= _day_start(now),
                    PrismRun.state.in_(COUNTED_STATES),
                )
            )
            or 0
        )

    @staticmethod
    def model_calls_today(db: Session, prism_id: uuid.UUID, now: datetime) -> int:
        results = db.scalars(
            select(PrismRun.result).where(
                PrismRun.prism_id == prism_id, PrismRun.started_at >= _day_start(now)
            )
        )
        return sum(int((r or {}).get("metrics", {}).get("model_calls", 0)) for r in results)

    @staticmethod
    def failure_streak(db: Session, prism_id: uuid.UUID) -> tuple[int, datetime | None]:
        """Consecutive failed runs (newest first) and when the latest one ended."""

        recent = list(
            db.execute(
                select(PrismRun.state, PrismRun.completed_at)
                .where(PrismRun.prism_id == prism_id, PrismRun.state.in_(("completed", "failed")))
                .order_by(PrismRun.completed_at.desc().nullslast(), PrismRun.id.desc())
                .limit(20)
            )
        )
        streak = 0
        for state, _ in recent:
            if state != "failed":
                break
            streak += 1
        return streak, (recent[0][1] if streak else None)

    @staticmethod
    def review_required(db: Session, prism_id: uuid.UUID) -> bool:
        """A migrated Prism may not monitor automatically until the user acknowledges it."""

        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(
                PrismWorkingAgreement.prism_id == prism_id,
                PrismWorkingAgreement.status == "confirmed",
            )
            .order_by(PrismWorkingAgreement.revision.desc())
        )
        return bool(agreement and agreement.generation_metadata.get("review_required"))

    @classmethod
    def block_reason(
        cls, db: Session, prism_id: uuid.UUID, trigger_type: str, now: datetime
    ) -> str | None:
        """Why an automatic run must not start. Manual runs are explicit and never blocked."""

        if trigger_type == "manual":
            return None
        if cls.review_required(db, prism_id):
            return "Skipped: review this migrated Prism before automatic monitoring."
        budget = PrismTuningService.budget(db, prism_id)
        if cls.runs_today(db, prism_id, now) >= budget["max_runs_per_day"]:
            return "Skipped: this Prism reached its daily run budget. It resets at midnight UTC."
        streak, last_failed_at = cls.failure_streak(db, prism_id)
        backoff = timedelta(minutes=get_settings().v22_failure_backoff_minutes)
        if (
            streak >= budget["max_consecutive_failures"]
            and last_failed_at is not None
            and last_failed_at > now - backoff
        ):
            return (
                f"Skipped: paused after {streak} failed runs in a row. "
                "It retries automatically after a short wait, or run it manually."
            )
        return None

    @classmethod
    def status(cls, db: Session, prism_id: uuid.UUID) -> dict:
        prism = PrismLifecycleService.get(db, prism_id)
        now = datetime.now(timezone.utc)
        settings = get_settings()
        policy = db.scalar(
            select(PrismTriggerPolicy).where(PrismTriggerPolicy.prism_id == prism_id)
        )
        connection = db.scalar(select(MicrosoftConnection).limit(1))
        last_ok = db.scalar(
            select(func.max(PrismRun.completed_at)).where(
                PrismRun.prism_id == prism_id, PrismRun.state == "completed"
            )
        )
        last_run = db.scalar(
            select(PrismRun)
            .where(PrismRun.prism_id == prism_id)
            .order_by(PrismRun.created_at.desc())
            .limit(1)
        )
        cursor_polled = db.scalar(
            select(func.max(PrismTeamsSourceCursor.last_polled_at)).where(
                PrismTeamsSourceCursor.prism_id == prism_id
            )
        )
        degraded_sources = int(
            db.scalar(
                select(func.count(PrismTeamsSourceCursor.id)).where(
                    PrismTeamsSourceCursor.prism_id == prism_id,
                    PrismTeamsSourceCursor.status == "degraded",
                )
            )
            or 0
        )
        streak, _ = cls.failure_streak(db, prism_id)
        budget = PrismTuningService.budget(db, prism_id)
        runs_today = cls.runs_today(db, prism_id, now)
        model_today = cls.model_calls_today(db, prism_id, now)
        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(
                PrismWorkingAgreement.prism_id == prism_id,
                PrismWorkingAgreement.status == "confirmed",
            )
            .order_by(PrismWorkingAgreement.revision.desc())
        )
        event_count = int(
            db.scalar(
                select(func.count(PrismExternalEvent.id)).where(
                    PrismExternalEvent.prism_id == prism_id
                )
            )
            or 0
        )
        queued = int(
            db.scalar(
                select(func.count(PrismRun.id)).where(
                    PrismRun.prism_id == prism_id, PrismRun.state == "queued"
                )
            )
            or 0
        )
        mode = policy.mode if policy else "manual"
        diagnosis: list[str] = []
        review_required = cls.review_required(db, prism_id)
        if review_required:
            diagnosis.append(
                "This Prism was migrated from v2.1. Review its agreement, then confirm below to allow automatic monitoring."
            )
        if prism.state.value.lower() != "active":
            diagnosis.append("This Prism is not active, so it is not monitoring.")
        if connection is None:
            diagnosis.append("Microsoft is not connected, so Prism cannot read Teams.")
        if mode == "manual":
            diagnosis.append("Monitoring is Manual only. Choose a schedule to check automatically.")
        elif not settings.prism_v22_scheduler_enabled:
            diagnosis.append(
                "The server scheduler is off. Set PRISM_V22_SCHEDULER_ENABLED=true and restart."
            )
        if queued > 5:
            diagnosis.append(
                f"{queued} runs are waiting in the queue; the scheduler may be stalled."
            )
        if streak >= budget["max_consecutive_failures"]:
            diagnosis.append(
                f"The last {streak} runs failed, so automatic runs are paused briefly."
            )
        if runs_today >= budget["max_runs_per_day"]:
            diagnosis.append("The daily run budget is used up; it resets at midnight UTC.")
        if degraded_sources:
            diagnosis.append(
                f"{degraded_sources} Teams chat(s) could not be read on the last check."
            )
        if agreement is None:
            diagnosis.append("No confirmed working agreement, so no signals are being evaluated.")
        if last_ok is None and last_run is not None and last_run.safe_error:
            diagnosis.append(f"Latest run: {last_run.safe_error}")
        if event_count == 0 and last_ok is not None:
            diagnosis.append("No Teams activity has been stored yet; check the monitoring scope.")
        if not diagnosis:
            diagnosis.append("Nothing is wrong. A quiet Prism means no signal matched.")
        return {
            "prism_id": prism_id,
            "provider": {
                "configured": bool(
                    settings.azure_openai_api_key and settings.azure_openai_endpoint
                ),
                "signal_model_enabled": settings.v22_signal_model_enabled,
            },
            "microsoft": {"connected": connection is not None},
            "scheduler": {
                "server_enabled": settings.prism_v22_scheduler_enabled,
                "mode": mode,
                "mode_enabled": bool(policy.enabled) if policy else False,
            },
            "monitoring": {
                "last_checked_at": cursor_polled,
                "last_successful_run_at": last_ok,
                "last_run_state": last_run.state if last_run else None,
                "last_run_error": last_run.safe_error if last_run else None,
                "degraded_sources": degraded_sources,
                "queued_runs": queued,
                "consecutive_failures": streak,
            },
            "budget": {
                **budget,
                "runs_today": runs_today,
                "model_calls_today": model_today,
            },
            "metrics": cls.metrics(db, prism_id, now),
            "diagnosis": diagnosis,
            "review_required": review_required,
            "retention_days": max(settings.v22_event_retention_days, 8),
        }

    @staticmethod
    def metrics(db: Session, prism_id: uuid.UUID, now: datetime) -> dict:
        since = now - timedelta(hours=24)
        runs = list(
            db.execute(
                select(
                    PrismRun.state, PrismRun.result, PrismRun.started_at, PrismRun.completed_at
                ).where(PrismRun.prism_id == prism_id, PrismRun.created_at >= since)
            )
        )
        totals = {
            "runs": 0,
            "failed": 0,
            "skipped": 0,
            "graph_reads": 0,
            "events_created": 0,
            "candidates": 0,
            "observations_created": 0,
            "model_calls": 0,
            "suppressed_by_preference": 0,
        }
        durations: list[int] = []
        for state, result, _, _ in runs:
            totals["runs"] += state in ("completed", "failed")
            totals["failed"] += state == "failed"
            totals["skipped"] += state == "skipped"
            metrics = (result or {}).get("metrics", {})
            for key in (
                "graph_reads",
                "events_created",
                "candidates",
                "observations_created",
                "model_calls",
                "suppressed_by_preference",
            ):
                totals[key] += int(metrics.get(key, 0))
            if "duration_ms" in metrics:
                durations.append(int(metrics["duration_ms"]))
        totals["avg_duration_ms"] = int(sum(durations) / len(durations)) if durations else None
        notifications = dict(
            db.execute(
                select(PrismNotification.result, func.count(PrismNotification.id))
                .where(
                    PrismNotification.prism_id == prism_id, PrismNotification.created_at >= since
                )
                .group_by(PrismNotification.result)
            ).all()
        )
        return {
            **totals,
            "notifications_delivered": int(notifications.get("delivered", 0)),
            "alerts_deduplicated": int(notifications.get("duplicate_incident", 0)),
            "alerts_suppressed": int(
                sum(
                    v
                    for k, v in notifications.items()
                    if k and k not in ("delivered", "duplicate_incident")
                )
            ),
            "drafts_prepared": int(
                db.scalar(
                    select(func.count(PrismObservationDraft.id)).where(
                        PrismObservationDraft.prism_id == prism_id,
                        PrismObservationDraft.created_at >= since,
                    )
                )
                or 0
            ),
            "false_positive_feedback": int(
                db.scalar(
                    select(func.count(PrismObservationFeedback.id)).where(
                        PrismObservationFeedback.prism_id == prism_id,
                        PrismObservationFeedback.created_at >= since,
                        PrismObservationFeedback.kind.in_(
                            ("not_helpful", "no_longer_relevant", "wrong_evidence")
                        ),
                    )
                )
                or 0
            ),
            "open_observations": int(
                db.scalar(
                    select(func.count(PrismObservation.id)).where(
                        PrismObservation.prism_id == prism_id, PrismObservation.state == "open"
                    )
                )
                or 0
            ),
        }
