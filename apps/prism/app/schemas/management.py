from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import Field

from app.models.enums import BlockerSeverity
from app.schemas.common import Schema


class RuleFinding(Schema):
    rule_code: str
    severity: BlockerSeverity
    reason: str
    employee_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    blocker_id: Optional[uuid.UUID] = None
    commitment_id: Optional[uuid.UUID] = None


class ProjectTargetDateChangeRequest(Schema):
    requested_target_date: date
    reason: str = Field(min_length=1)
