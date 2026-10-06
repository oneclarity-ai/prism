from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import TaskStatus
from app.schemas.common import Page
from app.schemas.escalation import EscalationRead
from app.schemas.task import TaskCreate, TaskDeadlineChangeRequest, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    return TaskService.create(db, payload)


@router.get("", response_model=Page[TaskRead])
def list_tasks(
    db: Session = Depends(get_db),
    status_filter: Optional[TaskStatus] = Query(default=None, alias="status"),
    owner_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TaskRead]:
    tasks, total = TaskService.list(
        db,
        status=status_filter,
        owner_id=owner_id,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return Page[TaskRead](items=tasks, total=total, limit=limit, offset=offset)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> TaskRead:
    return TaskService.get(db, task_id)


@router.post(
    "/{task_id}/deadline-change-requests",
    response_model=EscalationRead,
    status_code=status.HTTP_201_CREATED,
)
def request_task_deadline_change(
    task_id: uuid.UUID,
    payload: TaskDeadlineChangeRequest,
    db: Session = Depends(get_db),
) -> EscalationRead:
    return TaskService.request_deadline_change(db, task_id, payload)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: uuid.UUID, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    return TaskService.update(db, task_id, payload)
