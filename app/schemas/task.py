from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from app.models.enums import Priority, TaskStatus
from app.schemas.common import ORMResponse, Schema


class TaskCreate(Schema):
    owner_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    expected_outcome: str = Field(min_length=1)
    project_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    deadline: Optional[datetime] = None

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_timezone_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("deadline must include a timezone offset")
        return value


class TaskUpdate(Schema):
    project_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    expected_outcome: Optional[str] = Field(default=None, min_length=1)
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    deadline: Optional[datetime] = None

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_timezone_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("deadline must include a timezone offset")
        return value


class TaskDeadlineChangeRequest(Schema):
    requested_deadline: datetime
    reason: str = Field(min_length=1)

    @field_validator("requested_deadline")
    @classmethod
    def requested_deadline_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_deadline must include a timezone offset")
        return value


class TaskRead(ORMResponse):
    id: uuid.UUID
    project_id: Optional[uuid.UUID]
    owner_id: uuid.UUID
    title: str
    description: Optional[str]
    expected_outcome: Optional[str]
    status: TaskStatus
    priority: Priority
    deadline: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
