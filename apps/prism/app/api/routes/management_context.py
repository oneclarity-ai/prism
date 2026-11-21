import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.management_context import (
    ManagementContextCreate,
    ManagementContextRead,
    ManagementContextUpdate,
)
from app.services.deployment_list_service import DeploymentListService
from app.services.management_context_service import ManagementContextService

router = APIRouter(prefix="/api/v1/management-context", tags=["manager knowledge"])


@router.post("", response_model=ManagementContextRead, status_code=status.HTTP_201_CREATED)
def create_context(
    payload: ManagementContextCreate, db: Session = Depends(get_db)
) -> ManagementContextRead:
    return ManagementContextService.create(db, payload)


@router.get("", response_model=Page[ManagementContextRead])
def list_context(
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ManagementContextRead]:
    entries, total = ManagementContextService.list(db, limit=limit, offset=offset)
    return Page(items=entries, total=total, limit=limit, offset=offset)


@router.patch("/{entry_id}", response_model=ManagementContextRead)
def update_context(
    entry_id: uuid.UUID, payload: ManagementContextUpdate, db: Session = Depends(get_db)
) -> ManagementContextRead:
    return ManagementContextService.update(db, entry_id, payload)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    ManagementContextService.delete(db, entry_id)


@router.post("/{entry_id}/distribute-deployment-list")
def distribute_deployment_list(
    entry_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Explicitly distribute one saved deployment list to the active run."""

    return DeploymentListService.distribute(db, entry_id)
