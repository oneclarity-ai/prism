from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.memory.brain import BrainCreate, BrainRead, BrainUpdate
from app.services.memory.brain_service import BrainService

router = APIRouter(tags=["Brain"])


@router.get("/api/v2/brain", response_model=list[BrainRead])
def list_entries(db: Session = Depends(get_db)):
    """What every Prism knows: your entries, Prism work notes, and facts waiting for your approval."""

    return BrainService.list(db)


@router.post("/api/v2/brain", response_model=BrainRead, status_code=201)
def create_entry(payload: BrainCreate, db: Session = Depends(get_db)):
    return BrainService.create(db, payload.title, payload.body)


@router.patch("/api/v2/brain/{entry_id}", response_model=BrainRead)
def update_entry(entry_id: uuid.UUID, payload: BrainUpdate, db: Session = Depends(get_db)):
    return BrainService.update(db, entry_id, payload.title, payload.body)


@router.post("/api/v2/brain/{entry_id}/approve", response_model=BrainRead)
def approve_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)):
    return BrainService.decide(db, entry_id, True)


@router.post("/api/v2/brain/{entry_id}/reject", response_model=BrainRead)
def reject_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)):
    return BrainService.decide(db, entry_id, False)


@router.delete("/api/v2/brain/{entry_id}", status_code=204)
def delete_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    BrainService.delete(db, entry_id)
    return Response(status_code=204)
