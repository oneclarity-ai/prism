from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.project import Project
from app.services.errors import NotFoundError, RuleViolationError


def get_employee(db: Session, employee_id: object) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee was not found")
    return employee


def get_active_employee(db: Session, employee_id: object) -> Employee:
    employee = get_employee(db, employee_id)
    if not employee.is_active:
        raise RuleViolationError("Task and project ownership requires an active employee")
    return employee


def get_project(db: Session, project_id: object) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project was not found")
    return project


def validate_date_range(start_date: object, target_date: object) -> None:
    if start_date is not None and target_date is not None and target_date < start_date:
        raise RuleViolationError("target_date cannot be before start_date")
