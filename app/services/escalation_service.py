from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    ActivityEventType,
    EscalationDecisionType,
    EscalationStatus,
    EscalationType,
)
from app.models.escalation import Escalation
from app.models.escalation_decision import EscalationDecision
from app.models.task import Task
from app.schemas.escalation import EscalationCreate, EscalationDecisionCreate
from app.services.common import get_active_employee, get_employee, get_project, validate_date_range
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.memory_service import MemoryService

MANAGER_APPROVAL_TYPES = {
    EscalationType.ARCHITECTURE_CHANGE,
    EscalationType.PROJECT_DEADLINE_CHANGE,
    EscalationType.PRODUCTION_DEPLOYMENT,
    EscalationType.APPROVAL_REQUIRED,
}


class EscalationService:
    """Persist and enforce the small V1 manager-approval state machine."""

    @staticmethod
    def create(db: Session, data: EscalationCreate) -> Escalation:
        EscalationService._validate_links(db, data.employee_id, data.project_id, data.task_id)
        payload = data.model_dump()
        requires_approval = bool(
            data.requires_manager_approval or data.escalation_type in MANAGER_APPROVAL_TYPES
        )
        payload["requires_manager_approval"] = requires_approval
        payload["status"] = (
            EscalationStatus.PENDING_APPROVAL if requires_approval else EscalationStatus.OPEN
        )
        escalation = Escalation(**payload)
        db.add(escalation)
        try:
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.ESCALATION_CREATED,
                entity_type="escalation",
                entity_id=escalation.id,
                previous=None,
                current=EscalationService._snapshot(escalation),
                subject_employee_id=escalation.employee_id,
                project_id=escalation.project_id,
                task_id=escalation.task_id,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Escalation could not be saved") from exc
        db.refresh(escalation)
        return escalation

    @staticmethod
    def get(db: Session, escalation_id: uuid.UUID) -> Escalation:
        escalation = db.get(Escalation, escalation_id)
        if escalation is None:
            raise NotFoundError("Escalation was not found")
        return escalation

    @staticmethod
    def decisions(db: Session, escalation_id: uuid.UUID) -> list[EscalationDecision]:
        EscalationService.get(db, escalation_id)
        return list(
            db.scalars(
                select(EscalationDecision)
                .where(EscalationDecision.escalation_id == escalation_id)
                .order_by(EscalationDecision.decided_at)
            )
        )

    @staticmethod
    def list(
        db: Session,
        *,
        status: EscalationStatus | None,
        employee_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        requires_manager_approval: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Escalation], int]:
        statement = select(Escalation).order_by(Escalation.created_at.desc(), Escalation.id)
        count_statement = select(func.count()).select_from(Escalation)
        for column, value in [
            (Escalation.status, status),
            (Escalation.employee_id, employee_id),
            (Escalation.project_id, project_id),
            (Escalation.task_id, task_id),
            (Escalation.requires_manager_approval, requires_manager_approval),
        ]:
            if value is not None:
                statement = statement.where(column == value)
                count_statement = count_statement.where(column == value)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(
            count_statement
        ) or 0

    @staticmethod
    def approve(
        db: Session, escalation_id: uuid.UUID, data: EscalationDecisionCreate
    ) -> Escalation:
        escalation = EscalationService.get(db, escalation_id)
        EscalationService._require_pending_approval(escalation)
        approver = get_active_employee(db, data.decided_by)
        action = EscalationService._authorized_action_for(escalation, data.authorized_action)
        previous = EscalationService._snapshot(escalation)
        escalation.status = EscalationStatus.APPROVED
        db.add(
            EscalationDecision(
                escalation_id=escalation.id,
                decision=EscalationDecisionType.APPROVED,
                decided_by=approver.id,
                reason=data.reason,
                authorized_action=action,
            )
        )
        try:
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.ESCALATION_APPROVED,
                entity_type="escalation",
                entity_id=escalation.id,
                previous=previous,
                current=EscalationService._snapshot(escalation),
                subject_employee_id=escalation.employee_id,
                actor_employee_id=approver.id,
                project_id=escalation.project_id,
                task_id=escalation.task_id,
                reason=data.reason,
            )
            EscalationService._execute_authorized_action(db, escalation, approver.id, data.reason)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Escalation decision could not be saved") from exc
        db.refresh(escalation)
        return escalation

    @staticmethod
    def reject(db: Session, escalation_id: uuid.UUID, data: EscalationDecisionCreate) -> Escalation:
        escalation = EscalationService.get(db, escalation_id)
        EscalationService._require_pending_approval(escalation)
        decider = get_active_employee(db, data.decided_by)
        previous = EscalationService._snapshot(escalation)
        escalation.status = EscalationStatus.REJECTED
        db.add(
            EscalationDecision(
                escalation_id=escalation.id,
                decision=EscalationDecisionType.REJECTED,
                decided_by=decider.id,
                reason=data.reason,
                authorized_action=None,
            )
        )
        try:
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.ESCALATION_REJECTED,
                entity_type="escalation",
                entity_id=escalation.id,
                previous=previous,
                current=EscalationService._snapshot(escalation),
                subject_employee_id=escalation.employee_id,
                actor_employee_id=decider.id,
                project_id=escalation.project_id,
                task_id=escalation.task_id,
                reason=data.reason,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Escalation decision could not be saved") from exc
        db.refresh(escalation)
        return escalation

    @staticmethod
    def acknowledge(db: Session, escalation_id: uuid.UUID) -> Escalation:
        escalation = EscalationService.get(db, escalation_id)
        if escalation.status != EscalationStatus.OPEN:
            raise RuleViolationError("Only open, non-protected escalations can be acknowledged")
        previous = EscalationService._snapshot(escalation)
        escalation.status = EscalationStatus.ACKNOWLEDGED
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.ESCALATION_ACKNOWLEDGED,
            entity_type="escalation",
            entity_id=escalation.id,
            previous=previous,
            current=EscalationService._snapshot(escalation),
            subject_employee_id=escalation.employee_id,
            project_id=escalation.project_id,
            task_id=escalation.task_id,
        )
        db.commit()
        db.refresh(escalation)
        return escalation

    @staticmethod
    def resolve(db: Session, escalation_id: uuid.UUID) -> Escalation:
        escalation = EscalationService.get(db, escalation_id)
        if escalation.status in {EscalationStatus.RESOLVED, EscalationStatus.REJECTED}:
            raise RuleViolationError("Only active escalations can be resolved")
        if escalation.status == EscalationStatus.PENDING_APPROVAL:
            raise RuleViolationError(
                "A pending approval must be approved or rejected before resolution"
            )
        previous = EscalationService._snapshot(escalation)
        escalation.status = EscalationStatus.RESOLVED
        escalation.resolved_at = datetime.now(timezone.utc)
        db.flush()
        MemoryService.record_transition(
            db,
            event_type=ActivityEventType.ESCALATION_RESOLVED,
            entity_type="escalation",
            entity_id=escalation.id,
            previous=previous,
            current=EscalationService._snapshot(escalation),
            subject_employee_id=escalation.employee_id,
            project_id=escalation.project_id,
            task_id=escalation.task_id,
        )
        db.commit()
        db.refresh(escalation)
        return escalation

    @staticmethod
    def _execute_authorized_action(
        db: Session, escalation: Escalation, actor_employee_id: uuid.UUID, reason: str
    ) -> None:
        """Apply the only protected V1 mutations in the approval transaction."""
        if escalation.escalation_type == EscalationType.PROJECT_DEADLINE_CHANGE:
            if escalation.project is None or escalation.requested_target_date is None:
                raise RuleViolationError(
                    "Project deadline approval is missing its requested target date"
                )
            project = escalation.project
            validate_date_range(project.start_date, escalation.requested_target_date)
            previous = {"target_date": project.target_date}
            project.target_date = escalation.requested_target_date
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.PROJECT_TARGET_DATE_CHANGED,
                entity_type="project",
                entity_id=project.id,
                previous=previous,
                current={"target_date": project.target_date},
                actor_employee_id=actor_employee_id,
                project_id=project.id,
                reason=reason,
            )
        elif escalation.escalation_type == EscalationType.APPROVAL_REQUIRED and escalation.task_id:
            if escalation.requested_deadline is None:
                raise RuleViolationError("Task deadline approval is missing its requested deadline")
            task = db.get(Task, escalation.task_id)
            if task is None:
                raise NotFoundError("Task was not found")
            previous = {"deadline": task.deadline}
            task.deadline = escalation.requested_deadline
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.TASK_DEADLINE_CHANGED,
                entity_type="task",
                entity_id=task.id,
                previous=previous,
                current={"deadline": task.deadline},
                subject_employee_id=task.owner_id,
                actor_employee_id=actor_employee_id,
                project_id=task.project_id,
                task_id=task.id,
                reason=reason,
            )

    @staticmethod
    def _authorized_action_for(escalation: Escalation, requested: str | None) -> str | None:
        expected = None
        if escalation.escalation_type == EscalationType.PROJECT_DEADLINE_CHANGE:
            expected = "apply_project_target_date"
        elif escalation.escalation_type == EscalationType.APPROVAL_REQUIRED and escalation.task_id:
            expected = "apply_task_deadline"
        if requested is not None and requested != expected:
            raise RuleViolationError("This escalation cannot authorize the requested action")
        return expected

    @staticmethod
    def _require_pending_approval(escalation: Escalation) -> None:
        if not escalation.requires_manager_approval:
            raise RuleViolationError("This escalation does not require an approval decision")
        if escalation.status != EscalationStatus.PENDING_APPROVAL:
            raise RuleViolationError("Only pending approvals can be decided")

    @staticmethod
    def _validate_links(
        db: Session,
        employee_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
    ) -> None:
        if employee_id is not None:
            get_employee(db, employee_id)
        if project_id is not None:
            get_project(db, project_id)
        if task_id is not None and db.get(Task, task_id) is None:
            raise NotFoundError("Task was not found")

    @staticmethod
    def _snapshot(escalation: Escalation) -> dict[str, object]:
        return {
            "status": escalation.status,
            "requires_manager_approval": escalation.requires_manager_approval,
            "requested_target_date": escalation.requested_target_date,
            "requested_deadline": escalation.requested_deadline,
            "resolved_at": escalation.resolved_at,
        }
