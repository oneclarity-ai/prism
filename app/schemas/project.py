from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import Field, model_validator

from app.models.enums import Priority, ProjectStatus
from app.schemas.common import ORMResponse, Schema


class ProjectCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.PLANNING
    priority: Priority = Priority.MEDIUM
    owner_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    target_date: Optional[date] = None

    @model_validator(mode="after")
    def target_date_is_not_before_start_date(self) -> "ProjectCreate":
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ValueError("target_date cannot be before start_date")
        return self


class ProjectUpdate(Schema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    priority: Optional[Priority] = None
    owner_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    target_date: Optional[date] = None


class ProjectRead(ORMResponse):
    id: uuid.UUID
    name: str
    description: Optional[str]
    status: ProjectStatus
    priority: Priority
    owner_id: Optional[uuid.UUID]
    start_date: Optional[date]
    target_date: Optional[date]
    created_at: datetime
    updated_at: datetime
