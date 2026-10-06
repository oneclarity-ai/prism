from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.daily_update import DailyUpdateCreate, DailyUpdateRead, DailyUpdateUpdate
from app.services.daily_update_service import DailyUpdateService

router = APIRouter(prefix="/api/v1/daily-updates", tags=["daily updates"])


@router.post("", response_model=DailyUpdateRead, status_code=status.HTTP_201_CREATED)
def create_daily_update(payload: DailyUpdateCreate, db: Session = Depends(get_db)) -> DailyUpdateRead:
    return DailyUpdateService.create(db, payload)


@router.get("", response_model=Page[DailyUpdateRead])
def list_daily_updates(
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    update_date: Optional[date] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DailyUpdateRead]:
    updates, total = DailyUpdateService.list(
        db,
        employee_id=employee_id,
        update_date=update_date,
        limit=limit,
        offset=offset,
    )
    return Page[DailyUpdateRead](items=updates, total=total, limit=limit, offset=offset)


@router.get("/{daily_update_id}", response_model=DailyUpdateRead)
def get_daily_update(daily_update_id: uuid.UUID, db: Session = Depends(get_db)) -> DailyUpdateRead:
    return DailyUpdateService.get(db, daily_update_id)


@router.patch("/{daily_update_id}", response_model=DailyUpdateRead)
def update_daily_update(
    daily_update_id: uuid.UUID, payload: DailyUpdateUpdate, db: Session = Depends(get_db)
) -> DailyUpdateRead:
    return DailyUpdateService.update(db, daily_update_id, payload)
