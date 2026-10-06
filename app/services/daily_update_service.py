from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import ActivityEventType
from app.schemas.daily_update import DailyUpdateCreate, DailyUpdateUpdate
from app.services.common import get_active_employee
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.memory_service import MemoryService


class DailyUpdateService:
    @staticmethod
    def create(db: Session, data: DailyUpdateCreate) -> DailyUpdate:
        get_active_employee(db, data.employee_id)
        daily_update = DailyUpdate(**data.model_dump())
        db.add(daily_update)
        try:
            db.flush()
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.DAILY_UPDATE_CREATED,
                entity_type="daily_update",
                entity_id=daily_update.id,
                previous=None,
                current=DailyUpdateService._snapshot(daily_update),
                subject_employee_id=daily_update.employee_id,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A daily update already exists for this employee and date") from exc
        db.refresh(daily_update)
        return daily_update

    @staticmethod
    def get(db: Session, daily_update_id: uuid.UUID) -> DailyUpdate:
        daily_update = db.get(DailyUpdate, daily_update_id)
        if daily_update is None:
            raise NotFoundError("Daily update was not found")
        return daily_update

    @staticmethod
    def list(
        db: Session,
        *,
        employee_id: uuid.UUID | None,
        update_date: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DailyUpdate], int]:
        statement = (select(DailyUpdate).join(Employee, Employee.id == DailyUpdate.employee_id)
                     .where(Employee.is_active.is_(True))
                     .order_by(DailyUpdate.update_date.desc(), DailyUpdate.created_at.desc()))
        count_statement = (select(func.count()).select_from(DailyUpdate)
                           .join(Employee, Employee.id == DailyUpdate.employee_id)
                           .where(Employee.is_active.is_(True)))
        if employee_id is not None:
            statement = statement.where(DailyUpdate.employee_id == employee_id)
            count_statement = count_statement.where(DailyUpdate.employee_id == employee_id)
        if update_date is not None:
            statement = statement.where(DailyUpdate.update_date == update_date)
            count_statement = count_statement.where(DailyUpdate.update_date == update_date)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def update(
        db: Session, daily_update_id: uuid.UUID, data: DailyUpdateUpdate
    ) -> DailyUpdate:
        daily_update = DailyUpdateService.get(db, daily_update_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("update_date") is None and "update_date" in changes:
            raise RuleViolationError("update_date cannot be empty")
        if changes.get("today_summary") is None and "today_summary" in changes:
            raise RuleViolationError("today_summary cannot be empty")
        if changes.get("expected_outcome") is None and "expected_outcome" in changes:
            raise RuleViolationError("expected_outcome cannot be empty")
        previous = DailyUpdateService._snapshot(daily_update)
        for field, value in changes.items():
            setattr(daily_update, field, value)
        try:
            db.flush()
            current = DailyUpdateService._snapshot(daily_update)
            if current != previous:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.DAILY_UPDATE_CHANGED,
                    entity_type="daily_update",
                    entity_id=daily_update.id,
                    previous=previous,
                    current=current,
                    subject_employee_id=daily_update.employee_id,
                )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A daily update already exists for this employee and date") from exc
        db.refresh(daily_update)
        return daily_update

    @staticmethod
    def _snapshot(daily_update: DailyUpdate) -> dict[str, object]:
        return {
            "update_date": daily_update.update_date,
            "completed_summary": daily_update.completed_summary,
            "today_summary": daily_update.today_summary,
            "expected_outcome": daily_update.expected_outcome,
            "blocker_summary": daily_update.blocker_summary,
            "raw_message": daily_update.raw_message,
        }

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A daily update already exists for this employee and date") from exc
