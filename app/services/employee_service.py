from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.enums import ActivityEventType, TaskStatus
from app.models.task import Task
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services.common import get_active_employee, get_employee
from app.services.errors import ConflictError, RuleViolationError
from app.services.memory_service import MemoryService


class EmployeeService:
    @staticmethod
    def create(db: Session, data: EmployeeCreate) -> Employee:
        if data.manager_id is not None:
            get_active_employee(db, data.manager_id)

        employee = Employee(**data.model_dump())
        db.add(employee)
        EmployeeService._commit(db, "An employee with this email or Teams ID already exists")
        db.refresh(employee)
        return employee

    @staticmethod
    def get(db: Session, employee_id: uuid.UUID) -> Employee:
        return get_employee(db, employee_id)

    @staticmethod
    def list(
        db: Session, *, is_active: bool | None, limit: int, offset: int
    ) -> tuple[list[Employee], int]:
        statement = select(Employee).order_by(Employee.name, Employee.id)
        count_statement = select(func.count()).select_from(Employee)
        if is_active is not None:
            statement = statement.where(Employee.is_active.is_(is_active))
            count_statement = count_statement.where(Employee.is_active.is_(is_active))
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def update(db: Session, employee_id: uuid.UUID, data: EmployeeUpdate) -> Employee:
        employee = get_employee(db, employee_id)
        changes = data.model_dump(exclude_unset=True)

        if "manager_id" in changes:
            manager_id = changes["manager_id"]
            if manager_id == employee.id:
                raise RuleViolationError("An employee cannot manage themselves")
            if manager_id is not None:
                manager = get_active_employee(db, manager_id)
                EmployeeService._ensure_no_management_cycle(employee, manager)

        if changes.get("is_active") is False and employee.is_active:
            EmployeeService._ensure_no_open_owned_tasks(db, employee.id)

        previous_manager = employee.manager_id
        for field, value in changes.items():
            setattr(employee, field, value)
        try:
            db.flush()
            if employee.manager_id != previous_manager:
                MemoryService.record_transition(
                    db,
                    event_type=ActivityEventType.EMPLOYEE_MANAGER_CHANGED,
                    entity_type="employee",
                    entity_id=employee.id,
                    previous={"manager_id": previous_manager},
                    current={"manager_id": employee.manager_id},
                    subject_employee_id=employee.id,
                )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("An employee with this email or Teams ID already exists") from exc
        db.refresh(employee)
        return employee

    @staticmethod
    def _ensure_no_open_owned_tasks(db: Session, employee_id: uuid.UUID) -> None:
        open_task = db.scalar(
            select(Task.id)
            .where(
                Task.owner_id == employee_id,
                Task.status.not_in([TaskStatus.DONE, TaskStatus.CANCELLED]),
            )
            .limit(1)
        )
        if open_task is not None:
            raise RuleViolationError(
                "Reassign or close the employee's active tasks before deactivating them"
            )

    @staticmethod
    def _ensure_no_management_cycle(employee: Employee, proposed_manager: Employee) -> None:
        current: Employee | None = proposed_manager
        while current is not None:
            if current.id == employee.id:
                raise RuleViolationError("Manager assignment would create a reporting cycle")
            current = current.manager

    @staticmethod
    def _commit(db: Session, conflict_detail: str) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(conflict_detail) from exc
