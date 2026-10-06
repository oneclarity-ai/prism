from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.models.enums import BlockerSeverity, BlockerStatus, CommitmentStatus
from app.schemas.common import Schema


class JourneyEventRead(Schema):
    """One immutable fact in the agent's handling of a blocker."""

    event_type: str
    title: str
    detail: str
    occurred_at: datetime
    employee_id: Optional[uuid.UUID] = None
    message_id: Optional[uuid.UUID] = None


class JourneyCommitmentRead(Schema):
    id: uuid.UUID
    owner_name: str
    description: str
    deadline: datetime
    status: CommitmentStatus


class JourneyRead(Schema):
    """A read-only explanation of how one blocker moved through the agent."""

    blocker_id: uuid.UUID
    title: str
    description: str
    status: BlockerStatus
    severity: BlockerSeverity
    blocked_employee_name: str
    dependency_owner_name: Optional[str]
    started_at: datetime
    last_activity_at: datetime
    events: list[JourneyEventRead]
    commitments: list[JourneyCommitmentRead]
