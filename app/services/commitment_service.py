from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import ActivityEventType, BlockerStatus, CommitmentStatus, TaskStatus
from app.models.task import Task
from app.schemas.commitment import CommitmentCreate, CommitmentRevisionCreate
from app.services.common import get_active_employee
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.memory_service import MemoryService


class CommitmentService:
    @staticmethod
    def create(db: Session, data: CommitmentCreate, *, commit: bool = True) -> Commitment:
        CommitmentService._validate_links(db, data.employee_id, data.task_id, data.blocker_id)
        commitment = Commitment(**data.model_dump())
        db.add(commitment)
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.COMMITMENT_CREATED,
            entity_type="commitment",
            entity_id=commitment.id,
            previous=None,
            current=CommitmentService._snapshot(commitment),
            subject_employee_id=commitment.employee_id,
            task_id=commitment.task_id,
        )
        if commit:
            db.commit()
        db.refresh(commitment)
        return commitment

    @staticmethod
    def get(db: Session, commitment_id: uuid.UUID) -> Commitment:
        commitment = db.get(Commitment, commitment_id)
        if commitment is None:
            raise NotFoundError("Commitment was not found")
        return commitment

    @staticmethod
    def list(
        db: Session,
        *,
        status: CommitmentStatus | None,
        employee_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        blocker_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Commitment], int]:
        statement = (select(Commitment).join(Employee, Employee.id == Commitment.employee_id)
                     .where(Employee.is_active.is_(True))
                     .order_by(Commitment.deadline, Commitment.created_at))
        count_statement = (select(func.count()).select_from(Commitment)
                           .join(Employee, Employee.id == Commitment.employee_id)
                           .where(Employee.is_active.is_(True)))
        filters = [
            (Commitment.status, status),
            (Commitment.employee_id, employee_id),
            (Commitment.task_id, task_id),
            (Commitment.blocker_id, blocker_id),
        ]
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)
                count_statement = count_statement.where(column == value)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def mark_missed(
        db: Session, commitment_id: uuid.UUID, reason: str | None = None
    ) -> Commitment:
        commitment = CommitmentService.get(db, commitment_id)
        if commitment.status != CommitmentStatus.OPEN:
            raise RuleViolationError("Only open commitments can be marked missed")
        previous = CommitmentService._snapshot(commitment)
        commitment.status = CommitmentStatus.MISSED
        commitment.missed_at = datetime.now(timezone.utc)
        if reason is not None:
            commitment.missed_reason = reason
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.COMMITMENT_MISSED,
            entity_type="commitment",
            entity_id=commitment.id,
            previous=previous,
            current=CommitmentService._snapshot(commitment),
            subject_employee_id=commitment.employee_id,
            task_id=commitment.task_id,
            reason=reason,
            occurred_at=commitment.missed_at,
        )
        db.commit()
        db.refresh(commitment)
        return commitment

    @staticmethod
    def revise(
        db: Session, commitment_id: uuid.UUID, data: CommitmentRevisionCreate, *, commit: bool = True
    ) -> Commitment:
        original = CommitmentService.get(db, commitment_id)
        if original.status != CommitmentStatus.MISSED:
            raise RuleViolationError("Only a missed commitment can receive a revised ETA")
        if original.missed_at is None:
            raise RuleViolationError("A missed commitment must have a recorded missed timestamp")
        if data.deadline <= original.deadline:
            raise RuleViolationError("A revised ETA must be later than the original commitment deadline")

        CommitmentService._validate_links(
            db, original.employee_id, original.task_id, original.blocker_id
        )
        previous = CommitmentService._snapshot(original)
        original.missed_reason = data.missed_reason
        original.status = CommitmentStatus.SUPERSEDED
        revised = Commitment(
            employee_id=original.employee_id,
            task_id=original.task_id,
            blocker_id=original.blocker_id,
            description=data.description,
            deadline=data.deadline,
            revised_from_id=original.id,
            source_message_id=data.source_message_id,
            confidence=data.confidence,
        )
        db.add(revised)
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.COMMITMENT_REVISED,
            entity_type="commitment",
            entity_id=revised.id,
            previous=previous,
            current=CommitmentService._snapshot(revised),
            subject_employee_id=revised.employee_id,
            task_id=revised.task_id,
            reason=data.missed_reason,
        )
        if commit:
            db.commit()
        db.refresh(revised)
        return revised

    @staticmethod
    def history(db: Session, commitment_id: uuid.UUID) -> list[Commitment]:
        commitment = CommitmentService.get(db, commitment_id)
        root = commitment
        while root.revised_from_id is not None:
            root = CommitmentService.get(db, root.revised_from_id)

        history = [root]
        pending_ids = [root.id]
        while pending_ids:
            revisions = list(
                db.scalars(
                    select(Commitment)
                    .where(Commitment.revised_from_id.in_(pending_ids))
                    .order_by(Commitment.created_at, Commitment.id)
                )
            )
            history.extend(revisions)
            pending_ids = [revision.id for revision in revisions]
        return history

    @staticmethod
    def mark_overdue(db: Session, as_of: datetime | None = None) -> list[Commitment]:
        """Mark open commitments past their deadline as missed.

        A future scheduler may call this deterministic method. It does not send
        messages or infer a missed reason.
        """

        check_time = as_of or datetime.now(timezone.utc)
        overdue = list(
            db.scalars(
                select(Commitment).where(
                    Commitment.status == CommitmentStatus.OPEN,
                    Commitment.deadline < check_time,
                )
            )
        )
        if not overdue:
            return []
        previous = {commitment.id: CommitmentService._snapshot(commitment) for commitment in overdue}
        for commitment in overdue:
            commitment.status = CommitmentStatus.MISSED
            commitment.missed_at = check_time
        db.flush()
        for commitment in overdue:
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.COMMITMENT_MISSED,
                entity_type="commitment",
                entity_id=commitment.id,
                previous=previous[commitment.id],
                current=CommitmentService._snapshot(commitment),
                subject_employee_id=commitment.employee_id,
                task_id=commitment.task_id,
                occurred_at=commitment.missed_at or check_time,
            )
        db.commit()
        return overdue

    @staticmethod
    def complete(db: Session, commitment_id: uuid.UUID, *, commit: bool = True) -> Commitment:
        commitment = CommitmentService.get(db, commitment_id)
        if commitment.status != CommitmentStatus.OPEN:
            raise RuleViolationError("Only open commitments can be completed")
        previous = CommitmentService._snapshot(commitment)
        commitment.status = CommitmentStatus.COMPLETED
        commitment.completed_at = datetime.now(timezone.utc)
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.COMMITMENT_COMPLETED,
            entity_type="commitment",
            entity_id=commitment.id,
            previous=previous,
            current=CommitmentService._snapshot(commitment),
            subject_employee_id=commitment.employee_id,
            task_id=commitment.task_id,
            occurred_at=commitment.completed_at,
        )
        if commit:
            db.commit()
        db.refresh(commitment)
        return commitment

    @staticmethod
    def cancel(db: Session, commitment_id: uuid.UUID) -> Commitment:
        commitment = CommitmentService.get(db, commitment_id)
        if commitment.status != CommitmentStatus.OPEN:
            raise RuleViolationError("Only open commitments can be cancelled")
        commitment.status = CommitmentStatus.CANCELLED
        CommitmentService._commit(db)
        db.refresh(commitment)
        return commitment

    @staticmethod
    def _validate_links(
        db: Session,
        employee_id: uuid.UUID,
        task_id: uuid.UUID | None,
        blocker_id: uuid.UUID | None,
    ) -> None:
        get_active_employee(db, employee_id)
        task: Task | None = None
        blocker: Blocker | None = None
        if task_id is not None:
            task = db.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task was not found")
            if task.status in [TaskStatus.DONE, TaskStatus.CANCELLED]:
                raise RuleViolationError("A completed or cancelled task cannot receive a new commitment")
        if blocker_id is not None:
            blocker = db.get(Blocker, blocker_id)
            if blocker is None:
                raise NotFoundError("Blocker was not found")
            if blocker.status != BlockerStatus.OPEN:
                raise RuleViolationError("A resolved blocker cannot receive a new commitment")
            if blocker.dependency_owner_ids and employee_id not in blocker.dependency_owner_ids:
                raise RuleViolationError("Blocker commitments must belong to the dependency owner")
        if task is not None and blocker is not None and blocker.task_id not in (None, task.id):
            raise RuleViolationError("Commitment task and blocker links must refer to the same task")

    @staticmethod
    def _snapshot(commitment: Commitment) -> dict[str, object]:
        return {
            "description": commitment.description,
            "deadline": commitment.deadline,
            "status": commitment.status,
            "completed_at": commitment.completed_at,
            "missed_at": commitment.missed_at,
            "missed_reason": commitment.missed_reason,
            "revised_from_id": commitment.revised_from_id,
        }

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Commitment could not be saved") from exc
