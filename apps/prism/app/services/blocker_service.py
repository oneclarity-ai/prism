from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.employee import Employee
from app.models.enums import ActivityEventType, BlockerStatus, TaskStatus
from app.models.response_state import BlockerDependency
from app.models.task import Task
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.services.common import get_active_employee
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.memory_service import MemoryService


class BlockerService:
    @staticmethod
    def create(db: Session, data: BlockerCreate, *, commit: bool = True) -> Blocker:
        get_active_employee(db, data.blocked_employee_id)
        if data.dependency_owner_id is not None:
            get_active_employee(db, data.dependency_owner_id)

        task: Task | None = None
        if data.task_id is not None:
            task = db.get(Task, data.task_id)
            if task is None:
                raise NotFoundError("Task was not found")
            if task.owner_id != data.blocked_employee_id:
                raise RuleViolationError("A task blocker must reference that task's current owner")
            if task.status in [TaskStatus.DONE, TaskStatus.CANCELLED]:
                raise RuleViolationError("A completed or cancelled task cannot receive a blocker")

        payload = data.model_dump(exclude={"dependency_owner_ids"})
        owners = data.dependency_owner_ids or (
            [data.dependency_owner_id] if data.dependency_owner_id else []
        )
        BlockerService._validate_owners(db, data.blocked_employee_id, owners)
        payload["dependency_owner_id"] = owners[0] if owners else None
        blocker = Blocker(**payload)
        db.add(blocker)
        if task is not None:
            task.status = TaskStatus.BLOCKED
            task.completed_at = None
        try:
            db.flush()
            BlockerService._set_owners(db, blocker, owners)
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.BLOCKER_CREATED,
                entity_type="blocker",
                entity_id=blocker.id,
                previous=None,
                current=BlockerService._snapshot(blocker),
                subject_employee_id=blocker.blocked_employee_id,
                task_id=blocker.task_id,
            )
            if commit:
                db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Blocker could not be saved") from exc
        db.refresh(blocker)
        return blocker

    @staticmethod
    def get(db: Session, blocker_id: uuid.UUID) -> Blocker:
        blocker = db.get(Blocker, blocker_id)
        if blocker is None:
            raise NotFoundError("Blocker was not found")
        return blocker

    @staticmethod
    def list(
        db: Session,
        *,
        status: BlockerStatus | None,
        task_id: uuid.UUID | None,
        blocked_employee_id: uuid.UUID | None,
        dependency_owner_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Blocker], int]:
        statement = (
            select(Blocker)
            .join(Employee, Employee.id == Blocker.blocked_employee_id)
            .where(Employee.is_active.is_(True))
            .order_by(Blocker.created_at.desc(), Blocker.id)
        )
        count_statement = (
            select(func.count())
            .select_from(Blocker)
            .join(Employee, Employee.id == Blocker.blocked_employee_id)
            .where(Employee.is_active.is_(True))
        )
        filters = [
            (Blocker.status, status),
            (Blocker.task_id, task_id),
            (Blocker.blocked_employee_id, blocked_employee_id),
        ]
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)
                count_statement = count_statement.where(column == value)
        if dependency_owner_id is not None:
            owned = select(BlockerDependency.blocker_id).where(
                BlockerDependency.employee_id == dependency_owner_id,
                BlockerDependency.is_active.is_(True),
            )
            condition = or_(
                Blocker.id.in_(owned), Blocker.dependency_owner_id == dependency_owner_id
            )
            statement, count_statement = (
                statement.where(condition),
                count_statement.where(condition),
            )
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(
            count_statement
        ) or 0

    @staticmethod
    def update(
        db: Session, blocker_id: uuid.UUID, data: BlockerUpdate, *, commit: bool = True
    ) -> Blocker:
        blocker = BlockerService.get(db, blocker_id)
        if blocker.status == BlockerStatus.RESOLVED:
            raise RuleViolationError(
                "Resolved blockers are immutable; create a new blocker if work is blocked again"
            )

        changes = data.model_dump(exclude_unset=True)
        if "dependency_owner_id" in changes and changes["dependency_owner_id"] is not None:
            get_active_employee(db, changes["dependency_owner_id"])
        if changes.get("status") == BlockerStatus.OPEN:
            raise RuleViolationError(
                "An open blocker cannot be reopened through the update workflow"
            )

        previous = BlockerService._snapshot(blocker)
        owners = changes.pop("dependency_owner_ids", None)
        if owners is not None or "dependency_owner_id" in changes:
            owners = (
                owners
                if owners is not None
                else ([changes["dependency_owner_id"]] if changes["dependency_owner_id"] else [])
            )
            BlockerService._validate_owners(db, blocker.blocked_employee_id, owners)
            BlockerService._set_owners(db, blocker, owners)
            changes["dependency_owner_id"] = owners[0] if owners else None
        requested_status = changes.pop("status", None)
        for field, value in changes.items():
            setattr(blocker, field, value)
        if requested_status == BlockerStatus.RESOLVED:
            blocker.status = BlockerStatus.RESOLVED
            blocker.resolved_at = datetime.now(timezone.utc)
            if blocker.task_id is not None:
                task = db.get(Task, blocker.task_id)
                other_open_blocker = db.scalar(
                    select(Blocker.id)
                    .where(
                        Blocker.task_id == blocker.task_id,
                        Blocker.status == BlockerStatus.OPEN,
                        Blocker.id != blocker.id,
                    )
                    .limit(1)
                )
                if (
                    task is not None
                    and task.status == TaskStatus.BLOCKED
                    and other_open_blocker is None
                ):
                    task.status = TaskStatus.IN_PROGRESS
        try:
            db.flush()
            current = BlockerService._snapshot(blocker)
            if previous["dependency_owner_ids"] != current["dependency_owner_ids"]:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.BLOCKER_DEPENDENCY_OWNER_CHANGED,
                    entity_type="blocker",
                    entity_id=blocker.id,
                    previous={
                        "dependency_owner_id": previous["dependency_owner_id"],
                        "dependency_owner_ids": previous["dependency_owner_ids"],
                    },
                    current={
                        "dependency_owner_id": current["dependency_owner_id"],
                        "dependency_owner_ids": current["dependency_owner_ids"],
                    },
                    subject_employee_id=blocker.blocked_employee_id,
                    task_id=blocker.task_id,
                )
            if previous["status"] != current["status"]:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.BLOCKER_STATUS_CHANGED,
                    entity_type="blocker",
                    entity_id=blocker.id,
                    previous={"status": previous["status"]},
                    current={"status": current["status"]},
                    subject_employee_id=blocker.blocked_employee_id,
                    task_id=blocker.task_id,
                )
            if blocker.status == BlockerStatus.RESOLVED and blocker.resolved_at is not None:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.BLOCKER_RESOLVED,
                    entity_type="blocker",
                    entity_id=blocker.id,
                    previous=previous,
                    current=current,
                    subject_employee_id=blocker.blocked_employee_id,
                    task_id=blocker.task_id,
                    occurred_at=blocker.resolved_at,
                )
            if commit:
                db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Blocker could not be saved") from exc
        db.refresh(blocker)
        return blocker

    @staticmethod
    def _snapshot(blocker: Blocker) -> dict[str, object]:
        return {
            "dependency_owner_id": blocker.dependency_owner_id,
            "dependency_owner_ids": blocker.dependency_owner_ids,
            "status": blocker.status,
            "severity": blocker.severity,
            "description": blocker.description,
            "resolved_at": blocker.resolved_at,
        }

    @staticmethod
    def _validate_owners(db: Session, blocked_id, owners) -> None:
        for owner_id in owners:
            get_active_employee(db, owner_id)
            if owner_id == blocked_id:
                raise RuleViolationError(
                    "An external dependency cannot belong to the blocked employee"
                )

    @staticmethod
    def _set_owners(db: Session, blocker: Blocker, owners) -> None:
        owners = set(owners)
        existing = {item.employee_id: item for item in blocker.dependencies}
        for owner_id, item in existing.items():
            item.is_active = owner_id in owners
        for owner_id in owners - existing.keys():
            item = BlockerDependency(blocker_id=blocker.id, employee_id=owner_id, is_active=True)
            blocker.dependencies.append(item)
        db.flush()

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Blocker could not be saved") from exc
