from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import ORMResponse, Schema


class BrainCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)


class BrainUpdate(Schema):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    body: Optional[str] = Field(default=None, min_length=1, max_length=2000)


class BrainRead(ORMResponse):
    id: uuid.UUID
    title: str
    body: str
    status: Literal["approved", "proposed", "rejected"]
    source: Literal["user", "chat", "prism"]
    prism_id: Optional[uuid.UUID]
    prism_name: Optional[str] = None
    updated_at: datetime
