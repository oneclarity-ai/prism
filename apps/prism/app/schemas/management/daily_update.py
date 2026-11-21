from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMResponse, Schema


class DailyUpdateCreate(Schema):
    employee_id: uuid.UUID
    update_date: date
    completed_summary: Optional[str] = None
    today_summary: str = Field(min_length=1)
    expected_outcome: Optional[str] = Field(default=None, min_length=1)
    blocker_summary: Optional[str] = None
    raw_message: Optional[str] = None


class DailyUpdateUpdate(Schema):
    update_date: Optional[date] = None
    completed_summary: Optional[str] = None
    today_summary: Optional[str] = Field(default=None, min_length=1)
    expected_outcome: Optional[str] = Field(default=None, min_length=1)
    blocker_summary: Optional[str] = None
    raw_message: Optional[str] = None


class DailyUpdateRead(ORMResponse):
    id: uuid.UUID
    employee_id: uuid.UUID
    update_date: date
    completed_summary: Optional[str]
    today_summary: Optional[str]
    expected_outcome: Optional[str]
    blocker_summary: Optional[str]
    raw_message: Optional[str]
    created_at: datetime
    updated_at: datetime
