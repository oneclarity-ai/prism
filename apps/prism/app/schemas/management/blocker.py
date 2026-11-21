from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models.enums import BlockerSeverity, BlockerStatus
from app.schemas.common import ORMResponse, Schema


class BlockerCreate(Schema):
    blocked_employee_id: uuid.UUID
    description: str = Field(min_length=1)
    task_id: Optional[uuid.UUID] = None
    dependency_owner_id: Optional[uuid.UUID] = None
    dependency_owner_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    severity: BlockerSeverity = BlockerSeverity.MEDIUM


class BlockerUpdate(Schema):
    description: Optional[str] = Field(default=None, min_length=1)
    dependency_owner_id: Optional[uuid.UUID] = None
    dependency_owner_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=8)
    severity: Optional[BlockerSeverity] = None
    status: Optional[BlockerStatus] = None


class BlockerRead(ORMResponse):
    id: uuid.UUID
    task_id: Optional[uuid.UUID]
    blocked_employee_id: uuid.UUID
    dependency_owner_id: Optional[uuid.UUID]
    dependency_owner_ids: list[uuid.UUID]
    description: str
    status: BlockerStatus
    severity: BlockerSeverity
    created_at: datetime
    resolved_at: Optional[datetime]
    updated_at: datetime
