from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ProjectStatus
from app.schemas.common import Page
from app.schemas.escalation import EscalationRead
from app.schemas.management import ProjectTargetDateChangeRequest
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService.create(db, payload)


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    status_filter: Optional[ProjectStatus] = Query(default=None, alias="status"),
    owner_id: Optional[uuid.UUID] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProjectRead]:
    projects, total = ProjectService.list(
        db, status=status_filter, owner_id=owner_id, limit=limit, offset=offset
    )
    return Page[ProjectRead](items=projects, total=total, limit=limit, offset=offset)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService.get(db, project_id)


@router.post(
    "/{project_id}/target-date-change-requests",
    response_model=EscalationRead,
    status_code=status.HTTP_201_CREATED,
)
def request_project_target_date_change(
    project_id: uuid.UUID,
    payload: ProjectTargetDateChangeRequest,
    db: Session = Depends(get_db),
) -> EscalationRead:
    return ProjectService.request_target_date_change(db, project_id, payload)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectRead:
    return ProjectService.update(db, project_id, payload)
