from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import EscalationStatus
from app.schemas.common import Page
from app.schemas.escalation import (
    EscalationCreate,
    EscalationDecisionCreate,
    EscalationDecisionRead,
    EscalationRead,
)
from app.services.escalation_service import EscalationService

router = APIRouter(prefix="/api/v1/escalations", tags=["escalations"])


@router.post("", response_model=EscalationRead, status_code=status.HTTP_201_CREATED)
def create_escalation(payload: EscalationCreate, db: Session = Depends(get_db)) -> EscalationRead:
    return EscalationService.create(db, payload)


@router.get("", response_model=Page[EscalationRead])
def list_escalations(
    db: Session = Depends(get_db),
    status_filter: Optional[EscalationStatus] = Query(default=None, alias="status"),
    employee_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    task_id: Optional[uuid.UUID] = None,
    requires_manager_approval: Optional[bool] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EscalationRead]:
    escalations, total = EscalationService.list(
        db,
        status=status_filter,
        employee_id=employee_id,
        project_id=project_id,
        task_id=task_id,
        requires_manager_approval=requires_manager_approval,
        limit=limit,
        offset=offset,
    )
    return Page[EscalationRead](items=escalations, total=total, limit=limit, offset=offset)


@router.post("/{escalation_id}/acknowledge", response_model=EscalationRead)
def acknowledge_escalation(
    escalation_id: uuid.UUID, db: Session = Depends(get_db)
) -> EscalationRead:
    return EscalationService.acknowledge(db, escalation_id)


@router.post("/{escalation_id}/approve", response_model=EscalationRead)
def approve_escalation(
    escalation_id: uuid.UUID,
    payload: EscalationDecisionCreate,
    db: Session = Depends(get_db),
) -> EscalationRead:
    """Record the manager's decision and execute only the action it authorises."""

    return EscalationService.approve(db, escalation_id, payload)


@router.post("/{escalation_id}/reject", response_model=EscalationRead)
def reject_escalation(
    escalation_id: uuid.UUID,
    payload: EscalationDecisionCreate,
    db: Session = Depends(get_db),
) -> EscalationRead:
    return EscalationService.reject(db, escalation_id, payload)


@router.get("/{escalation_id}/decisions", response_model=list[EscalationDecisionRead])
def list_escalation_decisions(
    escalation_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[EscalationDecisionRead]:
    return EscalationService.decisions(db, escalation_id)


@router.post("/{escalation_id}/resolve", response_model=EscalationRead)
def resolve_escalation(escalation_id: uuid.UUID, db: Session = Depends(get_db)) -> EscalationRead:
    return EscalationService.resolve(db, escalation_id)


@router.get("/{escalation_id}", response_model=EscalationRead)
def get_escalation(escalation_id: uuid.UUID, db: Session = Depends(get_db)) -> EscalationRead:
    return EscalationService.get(db, escalation_id)
