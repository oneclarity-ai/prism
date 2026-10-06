from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import Field

from app.models.enums import (
    BlockerSeverity,
    EscalationDecisionType,
    EscalationStatus,
    EscalationType,
)
from app.schemas.common import ORMResponse, Schema


class EscalationCreate(Schema):
    escalation_type: EscalationType
    severity: BlockerSeverity = BlockerSeverity.MEDIUM
    reason: str = Field(min_length=1)
    employee_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    context: Optional[str] = None
    requires_manager_approval: bool = False
    requested_target_date: Optional[date] = None
    requested_deadline: Optional[datetime] = None


class EscalationDecisionCreate(Schema):
    decided_by: uuid.UUID
    reason: str = Field(min_length=1)
    authorized_action: Optional[str] = Field(default=None, min_length=1, max_length=100)


class EscalationDecisionRead(ORMResponse):
    id: uuid.UUID
    escalation_id: uuid.UUID
    decision: EscalationDecisionType
    decided_by: uuid.UUID
    decided_at: datetime
    reason: str
    authorized_action: Optional[str]


class EscalationRead(ORMResponse):
    id: uuid.UUID
    employee_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    task_id: Optional[uuid.UUID]
    escalation_type: EscalationType
    severity: BlockerSeverity
    reason: str
    context: Optional[str]
    requested_target_date: Optional[date]
    requested_deadline: Optional[datetime]
    status: EscalationStatus
    requires_manager_approval: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    updated_at: datetime
