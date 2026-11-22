from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMResponse, Schema

ManagementContextCategory = Literal[
    "team", "work", "people", "communication", "escalation", "other"
]


class ManagementContextCreate(Schema):
    category: ManagementContextCategory
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    is_active: bool = True


class ManagementContextUpdate(ManagementContextCreate):
    """A complete replacement keeps the manager's saved context unambiguous."""


class ManagementContextRead(ORMResponse):
    id: uuid.UUID
    category: ManagementContextCategory
    title: str
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
