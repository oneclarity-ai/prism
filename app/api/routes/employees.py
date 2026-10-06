from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate
from app.schemas.employee_alias import EmployeeAliasCreate, EmployeeAliasRead
from app.services.employee_alias_service import EmployeeAliasService
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)) -> EmployeeRead:
    return EmployeeService.create(db, payload)


@router.get("", response_model=Page[EmployeeRead])
def list_employees(
    db: Session = Depends(get_db),
    is_active: Optional[bool] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EmployeeRead]:
    employees, total = EmployeeService.list(db, is_active=is_active, limit=limit, offset=offset)
    return Page[EmployeeRead](items=employees, total=total, limit=limit, offset=offset)


@router.get("/{employee_id}", response_model=EmployeeRead)
def get_employee(employee_id: uuid.UUID, db: Session = Depends(get_db)) -> EmployeeRead:
    return EmployeeService.get(db, employee_id)


@router.patch("/{employee_id}", response_model=EmployeeRead)
def update_employee(
    employee_id: uuid.UUID, payload: EmployeeUpdate, db: Session = Depends(get_db)
) -> EmployeeRead:
    return EmployeeService.update(db, employee_id, payload)


@router.get("/{employee_id}/aliases", response_model=list[EmployeeAliasRead])
def list_employee_aliases(
    employee_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[EmployeeAliasRead]:
    """List manager-confirmed alternative names used for exact owner resolution."""

    return EmployeeAliasService.list(db, employee_id)


@router.post(
    "/{employee_id}/aliases", response_model=EmployeeAliasRead, status_code=status.HTTP_201_CREATED
)
def create_employee_alias(
    employee_id: uuid.UUID, payload: EmployeeAliasCreate, db: Session = Depends(get_db)
) -> EmployeeAliasRead:
    """Add an explicit alias; the agent never invents aliases through fuzzy matching."""

    return EmployeeAliasService.create(db, employee_id, payload)


@router.delete("/{employee_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_alias(
    employee_id: uuid.UUID, alias_id: uuid.UUID, db: Session = Depends(get_db)
) -> Response:
    EmployeeAliasService.delete(db, employee_id, alias_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
