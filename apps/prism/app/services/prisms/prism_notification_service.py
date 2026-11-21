"""Unread updates and at-most-once browser notification delivery for Prism v2.2.

The stored observation is the system of record. A notification row is only a
delivery attempt: it is claimed atomically by one live page, carries minimal
copy, and a denied or absent browser never affects monitoring or the update.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import PrismLifecycleState
from app.models.prisms.prism_v22 import (
    Prism,
    PrismIncidentEvent,
    PrismNotification,
    PrismNotificationSetting,
    PrismObservation,
    PrismPresence,
)
from app.schemas.prisms.prism_v22 import (
    PrismNotificationClaim,
    PrismNotificationSettingUpdate,
    PrismUpdateSummaryRead,
)
from app.services.errors import NotFoundError
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService

URGENCY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SIGNAL_LABELS = {
    "production_incident": "Possible production incident",
    "missed_deadline": "Deadline at risk",
    "blocker": "Blocked work",
    "unanswered_message": "Unanswered message",
    "customer_discussion": "Customer discussion",
}
CLAIM_BATCH = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrismNotificationService:
    @staticmethod
    def record(db: Session, observation_ids: list[uuid.UUID], now: datetime | None = None) -> None:
        """Create one delivery record per durably stored observation (idempotent)."""

        if not observation_ids:
            return
        rows = db.execute(
            select(PrismObservation.id, PrismObservation.prism_id, PrismObservation.incident_id)
            .where(PrismObservation.id.in_(observation_ids))
            .order_by(PrismObservation.created_at, PrismObservation.id)
        ).all()
        known = set(
            db.scalars(
                select(PrismNotification.observation_id).where(
                    PrismNotification.observation_id.in_(observation_ids)
                )
            )
        )
        for observation_id, prism_id, incident_id in rows:
            if observation_id in known:
                continue
            notification = PrismNotification(
                prism_id=prism_id, observation_id=observation_id, created_at=now or _now()
            )
            if incident_id is not None and PrismNotificationService._duplicate(
                db, incident_id, observation_id
            ):
                # The same incident was already alerted; this Prism keeps its own in-app update.
                notification.state = "skipped"
                notification.result = "duplicate_incident"
                notification.completed_at = _now()
            db.add(notification)
            db.flush()
        db.commit()

    @staticmethod
    def _duplicate(db: Session, incident_id: uuid.UUID, observation_id: uuid.UUID) -> bool:
        """True when another observation of this incident already has a live alert since it (re)opened."""

        db.execute(select(func.pg_advisory_xact_lock(incident_id.int & 0x7FFFFFFFFFFFFFFF)))
        boundary = db.scalar(
            select(func.max(PrismIncidentEvent.created_at)).where(
                PrismIncidentEvent.incident_id == incident_id,
                PrismIncidentEvent.event_type.in_(("opened", "reopened")),
            )
        )
        statement = (
            select(func.count(PrismNotification.id))
            .join(PrismObservation, PrismObservation.id == PrismNotification.observation_id)
            .where(
                PrismObservation.incident_id == incident_id,
                PrismNotification.observation_id != observation_id,
                PrismNotification.state.in_(("pending", "claimed", "delivered")),
            )
        )
        if boundary is not None:
            statement = statement.where(PrismNotification.created_at >= boundary)
        return bool(db.scalar(statement))

    @staticmethod
    def update_summaries(db: Session) -> list[PrismUpdateSummaryRead]:
        unread = (PrismObservation.read_at.is_(None)) & (PrismObservation.state != "superseded")
        urgent = PrismObservation.urgency.in_(("high", "critical")) & (
            PrismObservation.state == "open"
        )
        rows = db.execute(
            select(
                PrismObservation.prism_id,
                func.count(PrismObservation.id),
                func.count(PrismObservation.id).filter(urgent),
                func.max(PrismObservation.created_at),
            )
            .where(unread)
            .group_by(PrismObservation.prism_id)
        ).all()
        return [
            PrismUpdateSummaryRead(
                prism_id=prism_id, unread=count, urgent_unread=urgent_count, latest_unread_at=latest
            )
            for prism_id, count, urgent_count, latest in rows
        ]

    @staticmethod
    def mark_read(db: Session, prism_id: uuid.UUID, observation_ids: list[uuid.UUID]) -> int:
        PrismLifecycleService.get(db, prism_id)
        statement = (
            update(PrismObservation)
            .where(PrismObservation.prism_id == prism_id, PrismObservation.read_at.is_(None))
            .values(read_at=_now())
        )
        if observation_ids:
            statement = statement.where(PrismObservation.id.in_(observation_ids))
        count = db.execute(statement).rowcount
        db.commit()
        return int(count or 0)

    @staticmethod
    def get_setting(db: Session, prism_id: uuid.UUID) -> PrismNotificationSetting:
        PrismLifecycleService.get(db, prism_id)
        setting = db.get(PrismNotificationSetting, prism_id)
        if setting is None:
            setting = PrismNotificationSetting(prism_id=prism_id, enabled=False, min_urgency="high")
            db.add(setting)
            db.commit()
            db.refresh(setting)
        return setting

    @classmethod
    def update_setting(
        cls, db: Session, prism_id: uuid.UUID, payload: PrismNotificationSettingUpdate
    ) -> PrismNotificationSetting:
        setting = cls.get_setting(db, prism_id)
        setting.enabled = payload.enabled
        setting.min_urgency = payload.min_urgency
        db.commit()
        db.refresh(setting)
        return setting

    @staticmethod
    def heartbeat(db: Session, client_id: str) -> None:
        now = _now()
        presence = db.get(PrismPresence, client_id)
        if presence is None:
            db.add(PrismPresence(client_id=client_id, last_seen_at=now))
        else:
            presence.last_seen_at = now
        stale = now - timedelta(hours=1)
        db.execute(PrismPresence.__table__.delete().where(PrismPresence.last_seen_at < stale))
        db.commit()

    @staticmethod
    def _is_present(db: Session, client_id: str, now: datetime) -> bool:
        presence = db.get(PrismPresence, client_id)
        ttl = timedelta(seconds=get_settings().v22_presence_ttl_seconds)
        return presence is not None and presence.last_seen_at >= now - ttl

    @classmethod
    def claim_next(cls, db: Session, client_id: str) -> PrismNotificationClaim | None:
        """Atomically hand one eligible notification to one live page, or nothing.

        Ineligible rows are closed with a safe reason so they are never retried.
        A page with no fresh heartbeat claims nothing, so closing the page stops
        attempts while the in-app update stays unread.
        """

        now = _now()
        if not cls._is_present(db, client_id, now):
            return None
        expiry = now - timedelta(minutes=get_settings().v22_notification_expiry_minutes)
        pending = list(
            db.scalars(
                select(PrismNotification)
                .where(PrismNotification.state == "pending")
                .order_by(PrismNotification.created_at, PrismNotification.id)
                .limit(CLAIM_BATCH)
                .with_for_update(skip_locked=True)
            )
        )
        claim: PrismNotificationClaim | None = None
        for notification in pending:
            reason = cls._skip_reason(db, notification, expiry)
            if reason is not None:
                notification.state = "skipped"
                notification.result = reason
                notification.completed_at = now
                continue
            if claim is None:
                observation = db.get(PrismObservation, notification.observation_id)
                prism = db.get(Prism, notification.prism_id)
                notification.state = "claimed"
                notification.claimed_by = client_id
                notification.claimed_at = now
                claim = cls._claim_payload(notification, observation, prism)
        db.commit()
        return claim

    @staticmethod
    def _skip_reason(db: Session, notification: PrismNotification, expiry: datetime) -> str | None:
        observation = db.get(PrismObservation, notification.observation_id)
        prism = db.get(Prism, notification.prism_id)
        if observation is None or prism is None:
            return "missing"
        if prism.state != PrismLifecycleState.ACTIVE:
            return "prism_inactive"
        if observation.state != "open":
            return "resolved"
        if observation.read_at is not None:
            return "already_read"
        if notification.created_at < expiry:
            return "expired"
        setting = db.get(PrismNotificationSetting, prism.id)
        if setting is None or not setting.enabled:
            return "disabled"
        if URGENCY_RANK[observation.urgency] < URGENCY_RANK[setting.min_urgency]:
            return "below_threshold"
        return None

    @staticmethod
    def _claim_payload(
        notification: PrismNotification, observation: PrismObservation, prism: Prism
    ) -> PrismNotificationClaim:
        label = SIGNAL_LABELS.get(observation.signal_type, "New update")
        return PrismNotificationClaim(
            notification_id=notification.id,
            prism_id=prism.id,
            observation_id=observation.id,
            title=f"{prism.name}: {observation.urgency} update",
            body=f"{label}. Open Prism to review the evidence.",
            urgency=observation.urgency,
            tag=str(observation.id),
        )

    @staticmethod
    def report(db: Session, notification_id: uuid.UUID, client_id: str, result: str) -> None:
        """Record the one browser outcome; only the claiming page may report, once."""

        notification = db.get(PrismNotification, notification_id)
        if notification is None:
            raise NotFoundError("Notification not found")
        if notification.state != "claimed" or notification.claimed_by != client_id:
            return
        notification.state = "delivered" if result == "delivered" else "failed"
        notification.result = result
        notification.completed_at = _now()
        db.commit()
