"""Derived current organisational state. Operational rows remain authoritative."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.conversation import Conversation
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import BlockerStatus, CommitmentStatus, TaskStatus
from app.models.intelligence import ManagementRisk
from app.models.memory import ActivityEvent
from app.models.message import Message
from app.models.response_state import BlockerDependency, ConversationQuestion
from app.models.task import Task
from app.schemas.intelligence import EmployeeManagementState, StateItem
from app.services.errors import NotFoundError


class ManagementStateService:
    """Build one bounded, source-backed state object for a managed employee."""

    @staticmethod
    def employee_state(
        db: Session, employee_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> EmployeeManagementState:
        now = as_of or datetime.now(timezone.utc)
        local_now = now.astimezone(ZoneInfo(get_settings().manager_timezone))
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("Employee was not found")

        tasks = list(
            db.scalars(
                select(Task)
                .where(
                    Task.owner_id == employee_id,
                    Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                )
                .order_by(Task.updated_at.desc())
            )
        )
        blocked = list(
            db.scalars(
                select(Blocker)
                .where(
                    Blocker.blocked_employee_id == employee_id,
                    Blocker.status == BlockerStatus.OPEN,
                )
                .order_by(Blocker.updated_at.desc())
            )
        )
        owned_blocker_ids = set(
            db.scalars(
                select(BlockerDependency.blocker_id).where(
                    BlockerDependency.employee_id == employee_id,
                    BlockerDependency.is_active.is_(True),
                )
            )
        )
        owned_blockers = list(
            db.scalars(
                select(Blocker)
                .where(
                    Blocker.status == BlockerStatus.OPEN,
                    or_(
                        Blocker.dependency_owner_id == employee_id,
                        Blocker.id.in_(owned_blocker_ids),
                    ),
                )
                .order_by(Blocker.updated_at.desc())
            )
        )
        commitments = list(
            db.scalars(
                select(Commitment)
                .where(
                    Commitment.employee_id == employee_id,
                    Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.MISSED]),
                )
                .order_by(Commitment.deadline)
            )
        )

        questions = list(
            db.scalars(
                select(ConversationQuestion)
                .join(Conversation, Conversation.id == ConversationQuestion.conversation_id)
                .where(
                    ConversationQuestion.answered_at.is_(None),
                    or_(
                        ConversationQuestion.asked_to_employee_id == employee_id,
                        (ConversationQuestion.asked_to_employee_id.is_(None))
                        & (Conversation.employee_id == employee_id),
                    ),
                )
                .order_by(ConversationQuestion.created_at)
            )
        )
        recent_events = list(
            db.scalars(
                select(ActivityEvent)
                .where(
                    ActivityEvent.subject_employee_id == employee_id,
                    ActivityEvent.occurred_at >= now - timedelta(days=2),
                )
                .order_by(ActivityEvent.occurred_at.desc())
                .limit(30)
            )
        )
        completed_tasks = list(
            db.scalars(
                select(Task)
                .where(
                    Task.owner_id == employee_id,
                    Task.status == TaskStatus.DONE,
                    Task.completed_at >= now - timedelta(days=7),
                )
                .order_by(Task.completed_at.desc())
            )
        )
        today_update = db.scalar(
            select(DailyUpdate).where(
                DailyUpdate.employee_id == employee_id,
                DailyUpdate.update_date == local_now.date(),
            )
        )
        risks = [
            risk
            for risk in db.scalars(
                select(ManagementRisk)
                .where(ManagementRisk.status == "active")
                .order_by(ManagementRisk.severity.desc())
            )
            if str(employee_id)
            in {str(entity.get("id")) for entity in (risk.affected_entities or [])}
            or (risk.source_entity_type == "employee" and risk.source_entity_id == employee_id)
        ]

        active_work = [ManagementStateService._task_item(task) for task in tasks]
        if today_update and today_update.today_summary:
            active_work.insert(
                0,
                StateItem(
                    id=today_update.id,
                    kind="daily_update",
                    summary=today_update.today_summary,
                    status="current",
                    employee_id=employee_id,
                    occurred_at=datetime.combine(
                        today_update.update_date, datetime.min.time(), tzinfo=timezone.utc
                    ),
                    evidence=[f"daily_update:{today_update.id}"],
                ),
            )

        current_blockers = [ManagementStateService._blocker_item(item) for item in blocked]
        dependencies_on_others = [ManagementStateService._blocker_item(item) for item in blocked]
        others_depending = [ManagementStateService._blocker_item(item) for item in owned_blockers]
        open_commitments = [
            ManagementStateService._commitment_item(item)
            for item in commitments
            if item.status == CommitmentStatus.OPEN
        ]
        upcoming = [
            item
            for item in open_commitments
            if item.due_at and item.due_at <= now + timedelta(days=7)
        ]
        missed = [
            ManagementStateService._commitment_item(item)
            for item in commitments
            if item.status == CommitmentStatus.MISSED
        ]
        awaiting = [ManagementStateService._question_item(db, item) for item in questions]
        completed = [
            StateItem(
                id=task.id,
                kind="task",
                summary=task.title,
                status="done",
                employee_id=employee_id,
                task_id=task.id,
                project_id=task.project_id,
                occurred_at=task.completed_at,
                evidence=[f"task:{task.id}"],
            )
            for task in completed_tasks
        ]
        if today_update and today_update.completed_summary:
            completed.insert(
                0,
                StateItem(
                    id=today_update.id,
                    kind="daily_update",
                    summary=today_update.completed_summary,
                    status="completed",
                    employee_id=employee_id,
                    evidence=[f"daily_update:{today_update.id}"],
                ),
            )
        changes = [ManagementStateService._event_item(event) for event in recent_events]
        followups = list(awaiting) + list(missed)
        risk_items = [
            StateItem(
                id=risk.id,
                kind="risk",
                summary=risk.summary,
                status=risk.severity,
                employee_id=employee_id,
                due_at=risk.deadline_at_risk,
                occurred_at=risk.first_detected_at,
                evidence=[str(value) for value in risk.evidence],
            )
            for risk in risks
        ]

        return EmployeeManagementState(
            employee_id=employee.id,
            employee_name=employee.name,
            generated_at=now,
            active_work=active_work,
            current_blockers=current_blockers,
            dependencies_on_others=dependencies_on_others,
            others_depending_on_employee=others_depending,
            open_commitments=open_commitments,
            upcoming_deadlines=upcoming,
            missed_commitments=missed,
            awaiting_answers=awaiting,
            recently_completed=completed,
            recent_changes=changes,
            open_followups=followups,
            management_risks=risk_items,
        )

    @staticmethod
    def all_managed(db: Session, *, as_of: datetime | None = None) -> list[EmployeeManagementState]:
        employees = list(
            db.scalars(
                select(Employee)
                .where(Employee.is_active.is_(True), Employee.is_managed.is_(True))
                .order_by(Employee.name)
            )
        )
        return [
            ManagementStateService.employee_state(db, employee.id, as_of=as_of)
            for employee in employees
        ]

    @staticmethod
    def _task_item(task: Task) -> StateItem:
        return StateItem(
            id=task.id,
            kind="task",
            summary=task.title,
            status=task.status.value,
            employee_id=task.owner_id,
            task_id=task.id,
            project_id=task.project_id,
            due_at=task.deadline,
            evidence=[f"task:{task.id}"],
        )

    @staticmethod
    def _blocker_item(blocker: Blocker) -> StateItem:
        return StateItem(
            id=blocker.id,
            kind="blocker",
            summary=blocker.description,
            status=blocker.status.value,
            employee_id=blocker.blocked_employee_id,
            task_id=blocker.task_id,
            blocker_id=blocker.id,
            occurred_at=blocker.created_at,
            evidence=[f"blocker:{blocker.id}"],
        )

    @staticmethod
    def _commitment_item(commitment: Commitment) -> StateItem:
        return StateItem(
            id=commitment.id,
            kind="commitment",
            summary=commitment.description,
            status=commitment.status.value,
            employee_id=commitment.employee_id,
            task_id=commitment.task_id,
            blocker_id=commitment.blocker_id,
            commitment_id=commitment.id,
            due_at=commitment.deadline,
            occurred_at=commitment.committed_at,
            evidence=[f"commitment:{commitment.id}"]
            + ([f"message:{commitment.source_message_id}"] if commitment.source_message_id else []),
        )

    @staticmethod
    def _question_item(db: Session, question: ConversationQuestion) -> StateItem:
        message = db.get(Message, question.message_id)
        return StateItem(
            id=question.id,
            kind="question",
            summary=message.content if message else question.awaiting_field,
            status="awaiting_response",
            blocker_id=question.blocker_id,
            task_id=question.task_id,
            commitment_id=question.related_commitment_id,
            occurred_at=question.created_at,
            evidence=[f"question:{question.id}", f"message:{question.message_id}"],
        )

    @staticmethod
    def _event_item(event: ActivityEvent) -> StateItem:
        return StateItem(
            id=event.id,
            kind="change",
            summary=event.event_type.value.replace("_", " "),
            status="recorded",
            employee_id=event.subject_employee_id,
            task_id=event.task_id,
            project_id=event.project_id,
            occurred_at=event.occurred_at,
            evidence=[f"event:{event.id}"]
            + ([f"{event.source_type}:{event.source_id}"] if event.source_id else []),
        )
