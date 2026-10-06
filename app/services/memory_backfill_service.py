"""Safely queue existing local records as evidence for the memory engine."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.daily_update import DailyUpdate
from app.models.enums import (
    ActivityEventType,
    BlockerStatus,
    CommitmentStatus,
    EscalationStatus,
)
from app.models.escalation import Escalation
from app.models.message import Message
from app.services.memory_service import MemoryService


class MemoryBackfillService:
    """Queue missing event records only; no outside communication is performed."""

    @staticmethod
    def enqueue_existing_evidence(db: Session, *, limit: int = 500) -> dict[str, int]:
        result = {"messages": 0, "daily_updates": 0, "blockers": 0, "commitments": 0, "escalations": 0}
        for message in db.scalars(select(Message).order_by(Message.created_at).limit(limit)):
            before = MemoryBackfillService._exists(db, "message", message.id)
            MemoryService.record_message_evidence(db, message)
            result["messages"] += int(not before)
        for update in db.scalars(select(DailyUpdate).order_by(DailyUpdate.created_at).limit(limit)):
            before = MemoryBackfillService._exists(db, "daily_update", update.id)
            MemoryService.record_daily_update_event(db, update)
            result["daily_updates"] += int(not before)
        for blocker in db.scalars(select(Blocker).order_by(Blocker.created_at).limit(limit)):
            created = MemoryBackfillService._record(
                db, ActivityEventType.BLOCKER_CREATED, "blocker", blocker.id,
                blocker.created_at, blocker.blocked_employee_id, "blocker-created:{}".format(blocker.id),
            )
            result["blockers"] += int(created)
            if blocker.status == BlockerStatus.RESOLVED and blocker.resolved_at is not None:
                result["blockers"] += int(MemoryBackfillService._record(
                    db, ActivityEventType.BLOCKER_RESOLVED, "blocker", blocker.id,
                    blocker.resolved_at, blocker.blocked_employee_id, "blocker-resolved:{}".format(blocker.id),
                ))
        for commitment in db.scalars(select(Commitment).order_by(Commitment.committed_at).limit(limit)):
            result["commitments"] += int(MemoryBackfillService._record(
                db, ActivityEventType.COMMITMENT_CREATED, "commitment", commitment.id,
                commitment.committed_at, commitment.employee_id, "commitment-created:{}".format(commitment.id),
            ))
            final_event = {
                CommitmentStatus.COMPLETED: (ActivityEventType.COMMITMENT_COMPLETED, commitment.completed_at, "commitment-completed"),
                CommitmentStatus.MISSED: (ActivityEventType.COMMITMENT_MISSED, commitment.missed_at, "commitment-missed"),
                CommitmentStatus.SUPERSEDED: (ActivityEventType.COMMITMENT_REVISED, commitment.committed_at, "commitment-revised"),
            }.get(commitment.status)
            if final_event and final_event[1] is not None:
                result["commitments"] += int(MemoryBackfillService._record(
                    db, final_event[0], "commitment", commitment.id, final_event[1],
                    commitment.employee_id, "{}:{}".format(final_event[2], commitment.id),
                ))
        for escalation in db.scalars(select(Escalation).order_by(Escalation.created_at).limit(limit)):
            result["escalations"] += int(MemoryBackfillService._record(
                db, ActivityEventType.ESCALATION_CREATED, "escalation", escalation.id,
                escalation.created_at, escalation.employee_id, "escalation-created:{}".format(escalation.id),
            ))
            if escalation.status == EscalationStatus.RESOLVED and escalation.resolved_at is not None:
                result["escalations"] += int(MemoryBackfillService._record(
                    db, ActivityEventType.ESCALATION_RESOLVED, "escalation", escalation.id,
                    escalation.resolved_at, escalation.employee_id, "escalation-resolved:{}".format(escalation.id),
                ))
        db.commit()
        return result

    @staticmethod
    def _exists(db: Session, entity_type: str, entity_id: object) -> bool:
        from app.models.memory import ActivityEvent

        return db.scalar(select(ActivityEvent.id).where(ActivityEvent.entity_type == entity_type, ActivityEvent.entity_id == entity_id).limit(1)) is not None

    @staticmethod
    def _record(
        db: Session,
        event_type: ActivityEventType,
        entity_type: str,
        entity_id: object,
        occurred_at: datetime | None,
        employee_id: object,
        key: str,
    ) -> bool:
        from app.models.memory import ActivityEvent

        existed = db.scalar(select(ActivityEvent.id).where(ActivityEvent.idempotency_key == key).limit(1)) is not None
        MemoryService.record_event(
            db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source_type=entity_type,
            source_id=entity_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            subject_employee_id=employee_id,
            idempotency_key=key,
        )
        return not existed
