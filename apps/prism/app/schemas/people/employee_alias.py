from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import ORMResponse, Schema


class EmployeeAliasCreate(Schema):
    alias: str = Field(min_length=1, max_length=255)

    @field_validator("alias")
    @classmethod
    def clean_alias(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("alias cannot be blank")
        return value


class EmployeeAliasRead(ORMResponse):
    id: uuid.UUID
    employee_id: uuid.UUID
    alias: str
    created_at: datetime
    updated_at: datetime
