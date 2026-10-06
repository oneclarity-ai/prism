from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from app.schemas.common import ORMResponse, Schema

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class EmployeeCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=1, max_length=100)
    title: Optional[str] = Field(default=None, max_length=255)
    manager_id: Optional[uuid.UUID] = None
    teams_user_id: Optional[str] = Field(default=None, max_length=255)
    is_managed: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("must be a valid email address")
        return normalized


class EmployeeUpdate(Schema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[str] = Field(default=None, min_length=3, max_length=320)
    role: Optional[str] = Field(default=None, min_length=1, max_length=100)
    title: Optional[str] = Field(default=None, max_length=255)
    manager_id: Optional[uuid.UUID] = None
    teams_user_id: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None
    is_managed: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("must be a valid email address")
        return normalized


class EmployeeRead(ORMResponse):
    id: uuid.UUID
    name: str
    email: str
    role: str
    title: Optional[str]
    manager_id: Optional[uuid.UUID]
    teams_user_id: Optional[str]
    is_active: bool
    is_managed: bool
    aliases: list[str]
    created_at: datetime
    updated_at: datetime
