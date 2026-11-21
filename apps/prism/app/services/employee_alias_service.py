from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.employee_alias import EmployeeAlias
from app.schemas.employee_alias import EmployeeAliasCreate
from app.services.common import get_employee
from app.services.errors import ConflictError, NotFoundError, RuleViolationError


def normalize_alias(value: str) -> str:
    return " ".join(value.casefold().split())


class EmployeeAliasService:
    @staticmethod
    def list(db: Session, employee_id: uuid.UUID) -> list[EmployeeAlias]:
        get_employee(db, employee_id)
        return list(
            db.scalars(
                select(EmployeeAlias)
                .where(EmployeeAlias.employee_id == employee_id)
                .order_by(EmployeeAlias.alias, EmployeeAlias.id)
            )
        )

    @staticmethod
    def create(db: Session, employee_id: uuid.UUID, data: EmployeeAliasCreate) -> EmployeeAlias:
        employee = get_employee(db, employee_id)
        normalized = normalize_alias(data.alias)
        if normalized in {
            normalize_alias(employee.name),
            normalize_alias(employee.name.split()[0]),
        }:
            raise RuleViolationError("That alias is already part of this employee's name")

        # An alias must resolve to exactly one person. Do not let it shadow a
        # canonical full or first name already imported from Microsoft.
        employees = list(db.scalars(select(Employee).where(Employee.is_active.is_(True))))
        if any(
            other.id != employee.id
            and normalized in {normalize_alias(other.name), normalize_alias(other.name.split()[0])}
            for other in employees
        ):
            raise ConflictError("That alias matches another active employee")

        record = EmployeeAlias(
            employee_id=employee_id, alias=data.alias, normalized_alias=normalized
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("That alias is already assigned") from exc
        db.refresh(record)
        return record

    @staticmethod
    def delete(db: Session, employee_id: uuid.UUID, alias_id: uuid.UUID) -> None:
        record = db.scalar(
            select(EmployeeAlias).where(
                EmployeeAlias.id == alias_id, EmployeeAlias.employee_id == employee_id
            )
        )
        if record is None:
            raise NotFoundError("Employee alias was not found")
        db.delete(record)
        db.commit()
