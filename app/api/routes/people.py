from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.people import (
    PeopleRead,
    PeopleSyncResult,
    PersonUpdate,
    PrismPeopleRead,
    PrismPeopleUpdate,
)
from app.services.people_directory_service import PeopleDirectoryService

router = APIRouter(tags=["People"])


@router.get("/api/v1/people", response_model=PeopleRead)
def list_people(db: Session = Depends(get_db)) -> PeopleRead:
    """You, the people in your Teams chats, and the reporting lines between them."""

    return PeopleDirectoryService.overview(db)


@router.post("/api/v1/people/sync", response_model=PeopleSyncResult)
def sync_people(db: Session = Depends(get_db)) -> PeopleSyncResult:
    """Read chat participants and their Microsoft managers. Nobody is messaged."""

    return PeopleDirectoryService.sync(db)


@router.patch("/api/v1/people/{person_id}", response_model=PeopleRead)
def update_person(person_id: uuid.UUID, payload: PersonUpdate, db: Session = Depends(get_db)):
    PeopleDirectoryService.update(db, person_id, payload)
    return PeopleDirectoryService.overview(db)


@router.post("/api/v1/people/{person_id}/reset", response_model=PeopleRead)
def reset_person(person_id: uuid.UUID, db: Session = Depends(get_db)) -> PeopleRead:
    PeopleDirectoryService.reset(db, person_id)
    return PeopleDirectoryService.overview(db)


@router.get("/api/v2/prisms/{prism_id}/people", response_model=PrismPeopleRead)
def get_prism_people(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> PrismPeopleRead:
    scope, ids = PeopleDirectoryService.prism_people(db, prism_id)
    return PrismPeopleRead(scope=scope, employee_ids=ids)


@router.put("/api/v2/prisms/{prism_id}/people", response_model=PrismPeopleRead)
def set_prism_people(
    prism_id: uuid.UUID, payload: PrismPeopleUpdate, db: Session = Depends(get_db)
) -> PrismPeopleRead:
    scope, ids = PeopleDirectoryService.set_prism_people(
        db, prism_id, payload.scope, payload.employee_ids
    )
    return PrismPeopleRead(scope=scope, employee_ids=ids)
