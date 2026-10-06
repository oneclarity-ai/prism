from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import CommitmentStatus
from app.schemas.commitment import (
    CommitmentCreate,
    CommitmentMissed,
    CommitmentRead,
    CommitmentRevisionCreate,
)
from app.schemas.common import Page
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/api/v1/commitments", tags=["commitments"])


@router.post("", response_model=CommitmentRead, status_code=status.HTTP_201_CREATED)
def create_commitment(payload: CommitmentCreate, db: Session = Depends(get_db)) -> CommitmentRead:
    return CommitmentService.create(db, payload)


@router.get("", response_model=Page[CommitmentRead])
def list_commitments(
    db: Session = Depends(get_db),
    status_filter: Optional[CommitmentStatus] = Query(default=None, alias="status"),
    employee_id: Optional[uuid.UUID] = None,
    task_id: Optional[uuid.UUID] = None,
    blocker_id: Optional[uuid.UUID] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CommitmentRead]:
    commitments, total = CommitmentService.list(
        db,
        status=status_filter,
        employee_id=employee_id,
        task_id=task_id,
        blocker_id=blocker_id,
        limit=limit,
        offset=offset,
    )
    return Page[CommitmentRead](items=commitments, total=total, limit=limit, offset=offset)


@router.post("/{commitment_id}/mark-missed", response_model=CommitmentRead)
def mark_commitment_missed(
    commitment_id: uuid.UUID,
    payload: Optional[CommitmentMissed] = None,
    db: Session = Depends(get_db),
) -> CommitmentRead:
    return CommitmentService.mark_missed(db, commitment_id, payload.reason if payload else None)


@router.post("/{commitment_id}/revisions", response_model=CommitmentRead, status_code=status.HTTP_201_CREATED)
def revise_commitment(
    commitment_id: uuid.UUID,
    payload: CommitmentRevisionCreate,
    db: Session = Depends(get_db),
) -> CommitmentRead:
    return CommitmentService.revise(db, commitment_id, payload)


@router.get("/{commitment_id}/history", response_model=list[CommitmentRead])
def get_commitment_history(commitment_id: uuid.UUID, db: Session = Depends(get_db)) -> list[CommitmentRead]:
    return CommitmentService.history(db, commitment_id)


@router.post("/{commitment_id}/complete", response_model=CommitmentRead)
def complete_commitment(commitment_id: uuid.UUID, db: Session = Depends(get_db)) -> CommitmentRead:
    return CommitmentService.complete(db, commitment_id)


@router.post("/{commitment_id}/cancel", response_model=CommitmentRead)
def cancel_commitment(commitment_id: uuid.UUID, db: Session = Depends(get_db)) -> CommitmentRead:
    return CommitmentService.cancel(db, commitment_id)


@router.get("/{commitment_id}", response_model=CommitmentRead)
def get_commitment(commitment_id: uuid.UUID, db: Session = Depends(get_db)) -> CommitmentRead:
    return CommitmentService.get(db, commitment_id)
