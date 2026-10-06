from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.intelligence import ManagerFeedback
from app.models.message import Message
from app.models.project import Project
from app.schemas.intelligence import ManagerFeedbackCreate
from app.services.errors import NotFoundError


class ManagerFeedbackService:
    @staticmethod
    def create(db: Session, data: ManagerFeedbackCreate) -> ManagerFeedback:
        if data.employee_id and db.get(Employee, data.employee_id) is None:
            raise NotFoundError("Employee was not found")
        if data.project_id and db.get(Project, data.project_id) is None:
            raise NotFoundError("Project was not found")
        if data.source_message_id and db.get(Message, data.source_message_id) is None:
            raise NotFoundError("Source message was not found")
        item = ManagerFeedback(**data.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def applicable(
        db: Session, *, employee_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> list[ManagerFeedback]:
        now = as_of or datetime.now(timezone.utc)
        query = select(ManagerFeedback).where(
            ManagerFeedback.is_active.is_(True),
            or_(ManagerFeedback.expires_at.is_(None), ManagerFeedback.expires_at > now),
        )
        scopes = [ManagerFeedback.scope == "general", ManagerFeedback.scope == "one_time"]
        if employee_id:
            scopes.append((ManagerFeedback.scope == "person") & (ManagerFeedback.employee_id == employee_id))
        if project_id:
            scopes.append((ManagerFeedback.scope == "project") & (ManagerFeedback.project_id == project_id))
        return list(db.scalars(query.where(or_(*scopes)).order_by(ManagerFeedback.created_at.desc())))

    @staticmethod
    def deactivate(db: Session, feedback_id: uuid.UUID) -> ManagerFeedback:
        item = db.get(ManagerFeedback, feedback_id)
        if item is None:
            raise NotFoundError("Manager feedback was not found")
        item.is_active = False
        db.commit()
        db.refresh(item)
        return item

