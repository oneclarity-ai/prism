from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from app.models.enums import CommitmentStatus
from app.schemas.common import ORMResponse, Schema


class CommitmentCreate(Schema):
    employee_id: uuid.UUID
    description: str = Field(min_length=1)
    deadline: datetime
    task_id: Optional[uuid.UUID] = None
    blocker_id: Optional[uuid.UUID] = None
    source_message_id: Optional[uuid.UUID] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline must include a timezone offset")
        return value


class CommitmentMissed(Schema):
    reason: Optional[str] = Field(default=None, min_length=1)


class CommitmentRevisionCreate(Schema):
    description: str = Field(min_length=1)
    deadline: datetime
    missed_reason: str = Field(min_length=1)
    source_message_id: Optional[uuid.UUID] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline must include a timezone offset")
        return value


class CommitmentRead(ORMResponse):
    id: uuid.UUID
    employee_id: uuid.UUID
    task_id: Optional[uuid.UUID]
    blocker_id: Optional[uuid.UUID]
    description: str
    committed_at: datetime
    deadline: datetime
    status: CommitmentStatus
    completed_at: Optional[datetime]
    missed_at: Optional[datetime]
    missed_reason: Optional[str]
    revised_from_id: Optional[uuid.UUID]
    source_message_id: Optional[uuid.UUID]
    confidence: Optional[float]
    created_at: datetime
    updated_at: datetime
