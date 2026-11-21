from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import BlockerStatus
from app.schemas.blocker import BlockerCreate, BlockerRead, BlockerUpdate
from app.schemas.common import Page
from app.services.blocker_service import BlockerService

router = APIRouter(prefix="/api/v1/blockers", tags=["blockers"])


@router.post("", response_model=BlockerRead, status_code=status.HTTP_201_CREATED)
def create_blocker(payload: BlockerCreate, db: Session = Depends(get_db)) -> BlockerRead:
    return BlockerService.create(db, payload)


@router.get("", response_model=Page[BlockerRead])
def list_blockers(
    db: Session = Depends(get_db),
    status_filter: Optional[BlockerStatus] = Query(default=None, alias="status"),
    task_id: Optional[uuid.UUID] = None,
    blocked_employee_id: Optional[uuid.UUID] = None,
    dependency_owner_id: Optional[uuid.UUID] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[BlockerRead]:
    blockers, total = BlockerService.list(
        db,
        status=status_filter,
        task_id=task_id,
        blocked_employee_id=blocked_employee_id,
        dependency_owner_id=dependency_owner_id,
        limit=limit,
        offset=offset,
    )
    return Page[BlockerRead](items=blockers, total=total, limit=limit, offset=offset)


@router.get("/{blocker_id}", response_model=BlockerRead)
def get_blocker(blocker_id: uuid.UUID, db: Session = Depends(get_db)) -> BlockerRead:
    return BlockerService.get(db, blocker_id)


@router.patch("/{blocker_id}", response_model=BlockerRead)
def update_blocker(
    blocker_id: uuid.UUID, payload: BlockerUpdate, db: Session = Depends(get_db)
) -> BlockerRead:
    return BlockerService.update(db, blocker_id, payload)
