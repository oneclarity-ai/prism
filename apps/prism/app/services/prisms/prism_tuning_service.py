"""Prism-scoped feedback and signal tuning.

Feedback is recorded per observation. Learning only ever produces a *suggestion*; a
signal is muted only after the user confirms it, and a mandatory safety signal can
never be muted by preference (the agreement is the place to change it).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.prisms.prism_v22 import (
    PrismBudget,
    PrismObservation,
    PrismObservationFeedback,
    PrismSignalPreference,
)
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService

FEEDBACK_KINDS = (
    "helpful",
    "not_helpful",
    "wrong_urgency",
    "wrong_evidence",
    "duplicate",
    "no_longer_relevant",
)
OPPOSITES = {"helpful": "not_helpful", "not_helpful": "helpful"}
NEGATIVE = ("not_helpful", "no_longer_relevant")
SIGNALS = {
    "production_incident": "Production incidents",
    "missed_deadline": "Missed or threatened deadlines",
    "blocker": "Blocked work",
    "unanswered_message": "Important unanswered messages",
    "customer_discussion": "Important customer discussions",
}
MANDATORY = {"production_incident"}
SUGGEST_AFTER = 3
SUGGEST_WINDOW = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrismTuningService:
    @staticmethod
    def record_feedback(
        db: Session, prism_id: uuid.UUID, observation_id: uuid.UUID, kind: str
    ) -> list[str]:
        if kind not in FEEDBACK_KINDS:
            raise RuleViolationError("Unknown feedback type")
        observation = db.get(PrismObservation, observation_id)
        if observation is None or observation.prism_id != prism_id:
            raise NotFoundError("Observation not found")
        # Conflicting judgments on one observation: the latest wins.
        opposite = OPPOSITES.get(kind)
        if opposite:
            db.execute(
                delete(PrismObservationFeedback).where(
                    PrismObservationFeedback.observation_id == observation_id,
                    PrismObservationFeedback.kind == opposite,
                )
            )
        exists = db.scalar(
            select(PrismObservationFeedback.id).where(
                PrismObservationFeedback.observation_id == observation_id,
                PrismObservationFeedback.kind == kind,
            )
        )
        if exists is None:
            db.add(
                PrismObservationFeedback(
                    prism_id=prism_id,
                    observation_id=observation_id,
                    signal_type=observation.signal_type,
                    kind=kind,
                    created_at=_now(),
                )
            )
        db.commit()
        return PrismTuningService.feedback_kinds(db, [observation_id]).get(observation_id, [])

    @staticmethod
    def feedback_kinds(db: Session, observation_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        result: dict[uuid.UUID, list[str]] = {}
        if not observation_ids:
            return result
        for observation_id, kind in db.execute(
            select(PrismObservationFeedback.observation_id, PrismObservationFeedback.kind).where(
                PrismObservationFeedback.observation_id.in_(observation_ids)
            )
        ):
            result.setdefault(observation_id, []).append(kind)
        return result

    @staticmethod
    def muted_signals(db: Session, prism_id: uuid.UUID) -> set[str]:
        return (
            set(
                db.scalars(
                    select(PrismSignalPreference.signal_type).where(
                        PrismSignalPreference.prism_id == prism_id,
                        PrismSignalPreference.muted.is_(True),
                    )
                )
            )
            - MANDATORY
        )

    @staticmethod
    def record_suppressed(db: Session, prism_id: uuid.UUID, counts: dict[str, int]) -> None:
        for signal, count in counts.items():
            preference = db.get(PrismSignalPreference, (prism_id, signal))
            if preference is not None and count:
                preference.suppressed_count += count
                preference.last_applied_at = _now()

    @classmethod
    def tuning(cls, db: Session, prism_id: uuid.UUID) -> list[dict]:
        PrismLifecycleService.get(db, prism_id)
        since = _now() - SUGGEST_WINDOW
        counts: dict[tuple[str, str], int] = {}
        for signal, kind, total in db.execute(
            select(
                PrismObservationFeedback.signal_type,
                PrismObservationFeedback.kind,
                func.count(PrismObservationFeedback.id),
            )
            .where(
                PrismObservationFeedback.prism_id == prism_id,
                PrismObservationFeedback.created_at >= since,
            )
            .group_by(PrismObservationFeedback.signal_type, PrismObservationFeedback.kind)
        ):
            counts[(signal, kind)] = total
        preferences = {
            item.signal_type: item
            for item in db.scalars(
                select(PrismSignalPreference).where(PrismSignalPreference.prism_id == prism_id)
            )
        }
        signals = []
        for signal, label in SIGNALS.items():
            preference = preferences.get(signal)
            muted = bool(preference and preference.muted) and signal not in MANDATORY
            negative = sum(counts.get((signal, kind), 0) for kind in NEGATIVE)
            helpful = counts.get((signal, "helpful"), 0)
            suggestion = None
            if signal not in MANDATORY and not muted and negative >= SUGGEST_AFTER and not helpful:
                suggestion = (
                    f"You marked {negative} of these updates as not useful and none as helpful "
                    "in the last 30 days. Mute this signal for this Prism?"
                )
            signals.append(
                {
                    "signal_type": signal,
                    "label": label,
                    "protected": signal in MANDATORY,
                    "muted": muted,
                    "suppressed_count": preference.suppressed_count if preference else 0,
                    "last_applied_at": preference.last_applied_at if preference else None,
                    "feedback": {
                        kind: counts.get((signal, kind), 0)
                        for kind in FEEDBACK_KINDS
                        if counts.get((signal, kind), 0)
                    },
                    "suggestion": suggestion,
                }
            )
        return signals

    @staticmethod
    def set_muted(db: Session, prism_id: uuid.UUID, signal_type: str, muted: bool) -> None:
        PrismLifecycleService.get(db, prism_id)
        if signal_type not in SIGNALS:
            raise NotFoundError("Unknown signal")
        if muted and signal_type in MANDATORY:
            raise RuleViolationError(
                "Production incidents are a safety signal and can't be muted here. "
                "Remove it from this Prism's working agreement if you no longer want it."
            )
        preference = db.get(PrismSignalPreference, (prism_id, signal_type))
        if preference is None:
            preference = PrismSignalPreference(prism_id=prism_id, signal_type=signal_type)
            db.add(preference)
        preference.muted = muted
        db.commit()

    @staticmethod
    def budget(db: Session, prism_id: uuid.UUID) -> dict:
        """Effective limits: this Prism's override, else the safe global default."""

        settings = get_settings()
        override = db.get(PrismBudget, prism_id)
        return {
            "max_runs_per_day": (override and override.max_runs_per_day)
            or settings.v22_max_runs_per_day,
            "max_model_calls_per_day": settings.v22_max_model_calls_per_day
            if override is None or override.max_model_calls_per_day is None
            else override.max_model_calls_per_day,
            "max_consecutive_failures": (override and override.max_consecutive_failures)
            or settings.v22_max_consecutive_failures,
            "customized": override is not None,
        }

    @staticmethod
    def update_budget(db: Session, prism_id: uuid.UUID, values: dict) -> None:
        PrismLifecycleService.get(db, prism_id)
        override = db.get(PrismBudget, prism_id)
        if override is None:
            override = PrismBudget(prism_id=prism_id)
            db.add(override)
        for key, value in values.items():
            setattr(override, key, value)
        db.commit()
