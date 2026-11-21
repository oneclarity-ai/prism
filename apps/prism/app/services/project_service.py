from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import ActivityEventType, BlockerSeverity, EscalationType, ProjectStatus
from app.models.escalation import Escalation
from app.models.project import Project
from app.schemas.escalation import EscalationCreate
from app.schemas.management import ProjectTargetDateChangeRequest
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.common import get_active_employee, get_project, validate_date_range
from app.services.errors import ConflictError, RuleViolationError
from app.services.escalation_service import EscalationService
from app.services.memory_service import MemoryService


class ProjectService:
    @staticmethod
    def create(db: Session, data: ProjectCreate) -> Project:
        if data.owner_id is not None:
            get_active_employee(db, data.owner_id)
        project = Project(**data.model_dump())
        db.add(project)
        ProjectService._commit(db)
        db.refresh(project)
        return project

    @staticmethod
    def get(db: Session, project_id: uuid.UUID) -> Project:
        return get_project(db, project_id)

    @staticmethod
    def list(
        db: Session,
        *,
        status: ProjectStatus | None,
        owner_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Project], int]:
        statement = select(Project).order_by(Project.created_at.desc(), Project.id)
        count_statement = select(func.count()).select_from(Project)
        if status is not None:
            statement = statement.where(Project.status == status)
            count_statement = count_statement.where(Project.status == status)
        if owner_id is not None:
            statement = statement.where(Project.owner_id == owner_id)
            count_statement = count_statement.where(Project.owner_id == owner_id)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(
            count_statement
        ) or 0

    @staticmethod
    def update(db: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
        project = get_project(db, project_id)
        changes = data.model_dump(exclude_unset=True)
        if "owner_id" in changes and changes["owner_id"] is not None:
            get_active_employee(db, changes["owner_id"])
        if "target_date" in changes and changes["target_date"] != project.target_date:
            raise RuleViolationError(
                "Project target date changes require the escalation and approval workflow"
            )

        start_date = changes.get("start_date", project.start_date)
        target_date = changes.get("target_date", project.target_date)
        validate_date_range(start_date, target_date)
        previous_owner = project.owner_id
        for field, value in changes.items():
            setattr(project, field, value)
        try:
            db.flush()
            if project.owner_id != previous_owner:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.PROJECT_OWNER_CHANGED,
                    entity_type="project",
                    entity_id=project.id,
                    previous={"owner_id": previous_owner},
                    current={"owner_id": project.owner_id},
                    project_id=project.id,
                )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Project could not be saved") from exc
        db.refresh(project)
        return project

    @staticmethod
    def request_target_date_change(
        db: Session, project_id: uuid.UUID, data: ProjectTargetDateChangeRequest
    ) -> Escalation:
        project = get_project(db, project_id)
        if project.target_date == data.requested_target_date:
            raise RuleViolationError("Requested target date is already the project's target date")
        validate_date_range(project.start_date, data.requested_target_date)
        context = "Current target date: {}; requested target date: {}".format(
            project.target_date.isoformat() if project.target_date else "not set",
            data.requested_target_date.isoformat(),
        )
        return EscalationService.create(
            db,
            EscalationCreate(
                escalation_type=EscalationType.PROJECT_DEADLINE_CHANGE,
                severity=BlockerSeverity.HIGH,
                reason=data.reason,
                project_id=project.id,
                context=context,
                requested_target_date=data.requested_target_date,
            ),
        )

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("Project could not be saved") from exc
