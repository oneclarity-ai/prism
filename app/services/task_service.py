from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.enums import ActivityEventType, BlockerSeverity, EscalationType, BlockerStatus, TaskStatus
from app.models.escalation import Escalation
from app.models.task import Task
from app.schemas.escalation import EscalationCreate
from app.schemas.task import TaskCreate, TaskDeadlineChangeRequest, TaskUpdate
from app.services.common import get_active_employee, get_project
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.escalation_service import EscalationService
from app.services.memory_service import MemoryService


class TaskService:
    @staticmethod
    def create(db: Session, data: TaskCreate, *, commit: bool = True) -> Task:
        TaskService._validate_owner_and_project(db, data.owner_id, data.project_id)
        if data.status == TaskStatus.BLOCKED:
            raise RuleViolationError("Use the blocker workflow to mark a task as blocked")

        task = Task(**data.model_dump())
        if task.status == TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
        db.add(task)
        if commit:
            TaskService._commit(db)
            db.refresh(task)
        else:
            db.flush()
        return task

    @staticmethod
    def get(db: Session, task_id: uuid.UUID) -> Task:
        task = db.get(Task, task_id)
        if task is None:
            raise NotFoundError("Task was not found")
        return task

    @staticmethod
    def list(
        db: Session,
        *,
        status: TaskStatus | None,
        owner_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        statement = select(Task).order_by(Task.deadline.is_(None), Task.deadline, Task.created_at.desc())
        count_statement = select(func.count()).select_from(Task)
        if status is not None:
            statement = statement.where(Task.status == status)
            count_statement = count_statement.where(Task.status == status)
        if owner_id is not None:
            statement = statement.where(Task.owner_id == owner_id)
            count_statement = count_statement.where(Task.owner_id == owner_id)
        if project_id is not None:
            statement = statement.where(Task.project_id == project_id)
            count_statement = count_statement.where(Task.project_id == project_id)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def update(
        db: Session, task_id: uuid.UUID, data: TaskUpdate, *, commit: bool = True
    ) -> Task:
        task = TaskService.get(db, task_id)
        changes = data.model_dump(exclude_unset=True)

        owner_id = changes.get("owner_id", task.owner_id)
        project_id = changes.get("project_id", task.project_id)
        TaskService._validate_owner_and_project(db, owner_id, project_id)
        if "expected_outcome" in changes and changes["expected_outcome"] is None:
            raise RuleViolationError("A meaningful task cannot have an empty expected outcome")
        if "deadline" in changes and changes["deadline"] != task.deadline:
            raise RuleViolationError("Task deadline changes require an explicit deadline-change workflow")
        if changes.get("status") == TaskStatus.BLOCKED:
            raise RuleViolationError("Use the blocker workflow to mark a task as blocked")
        if TaskService._has_open_blockers(db, task.id):
            if changes.get("owner_id") not in (None, task.owner_id):
                raise RuleViolationError("Resolve open blockers before reassigning this task")
            if "status" in changes and changes["status"] != TaskStatus.BLOCKED:
                raise RuleViolationError("Resolve open blockers before changing this task out of blocked status")

        previous_owner = task.owner_id
        for field, value in changes.items():
            setattr(task, field, value)
        if changes.get("status") == TaskStatus.DONE and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        elif "status" in changes and changes["status"] != TaskStatus.DONE:
            task.completed_at = None
        try:
            db.flush()
            if task.owner_id != previous_owner:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.TASK_OWNER_CHANGED,
                    entity_type="task",
                    entity_id=task.id,
                    previous={"owner_id": previous_owner},
                    current={"owner_id": task.owner_id},
                    subject_employee_id=task.owner_id,
                    project_id=task.project_id,
                    task_id=task.id,
                )
            if commit:
                db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Task could not be saved") from exc
        if commit:
            db.refresh(task)
        return task

    @staticmethod
    def request_deadline_change(
        db: Session, task_id: uuid.UUID, data: TaskDeadlineChangeRequest
    ) -> Escalation:
        task = TaskService.get(db, task_id)
        if task.deadline == data.requested_deadline:
            raise RuleViolationError("Requested deadline is already the task's deadline")
        return EscalationService.create(
            db,
            EscalationCreate(
                escalation_type=EscalationType.APPROVAL_REQUIRED,
                severity=BlockerSeverity.HIGH,
                reason=data.reason,
                employee_id=task.owner_id,
                project_id=task.project_id,
                task_id=task.id,
                context="Current deadline: {}; requested deadline: {}".format(
                    task.deadline.isoformat() if task.deadline else "not set",
                    data.requested_deadline.isoformat(),
                ),
                requested_deadline=data.requested_deadline,
            ),
        )

    @staticmethod
    def _validate_owner_and_project(
        db: Session, owner_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> None:
        get_active_employee(db, owner_id)
        if project_id is not None:
            get_project(db, project_id)

    @staticmethod
    def _has_open_blockers(db: Session, task_id: uuid.UUID) -> bool:
        return db.scalar(
            select(Blocker.id)
            .where(Blocker.task_id == task_id, Blocker.status == BlockerStatus.OPEN)
            .limit(1)
        ) is not None

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Task could not be saved") from exc
