from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.enums import (
    ActionProposalState,
    AgentJobState,
    AgentStepState,
    ApprovalDecisionType,
    ToolExecutionState,
)
from app.schemas.common import ORMResponse, Schema


class AgentSourceRead(Schema):
    kind: str
    external_id: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentThreadCreate(Schema):
    title: str = Field(min_length=1, max_length=255)
    source: AgentSourceRead | None = None


class AgentThreadRead(ORMResponse):
    id: uuid.UUID
    title: str
    source_kind: str | None
    source_external_id: str | None
    source_label: str | None
    source_metadata: dict[str, Any]
    is_canonical: bool
    created_at: datetime
    updated_at: datetime


class AgentThreadMessageCreate(Schema):
    content: str = Field(min_length=1, max_length=4000)
    source_external_id: str | None = Field(default=None, max_length=512)
    # Explicit source selection is scoped to this request. The server still
    # validates every id against the connected manager's Teams catalog.
    source_external_ids: list[str] = Field(default_factory=list, max_length=12)


class AgentThreadMessageRead(ORMResponse):
    id: uuid.UUID
    thread_id: uuid.UUID
    job_id: uuid.UUID | None
    role: str
    content: str
    message_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AgentPreferenceCreate(Schema):
    instruction: str = Field(min_length=3, max_length=4000)
    scope: str = Field(default="general", pattern=r"^(general|teams_chat)$")
    source_thread_id: uuid.UUID | None = None


class AgentPreferenceUpdate(Schema):
    instruction: str = Field(min_length=3, max_length=4000)
    scope: str = Field(pattern=r"^(general|teams_chat)$")
    is_active: bool


class AgentPreferenceRead(ORMResponse):
    id: uuid.UUID
    instruction: str
    scope: str
    source_kind: str
    source_thread_id: uuid.UUID | None
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentFeedbackCreate(Schema):
    event_type: str = Field(pattern=r"^(regeneration_requested|job_cancelled)$")
    details: dict[str, Any] = Field(default_factory=dict)


class AgentStepCreate(Schema):
    kind: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=255)


class AgentStepTransition(Schema):
    target: AgentStepState
    safe_error_code: str | None = Field(default=None, max_length=80)
    safe_error_detail: str | None = Field(default=None, max_length=1000)


class AgentStepRead(ORMResponse):
    id: uuid.UUID
    sequence: int
    kind: str
    label: str
    state: AgentStepState
    safe_error_code: str | None
    safe_error_detail: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentJobCreate(Schema):
    goal: str = Field(min_length=1, max_length=4000)


class AgentJobTransition(Schema):
    target: AgentJobState
    expected_version: int = Field(ge=1)
    safe_error_code: str | None = Field(default=None, max_length=80)
    safe_error_detail: str | None = Field(default=None, max_length=1000)


class AgentJobSourceRead(ORMResponse):
    id: uuid.UUID
    source_kind: str
    external_id: str
    label: str | None
    source_metadata: dict[str, Any]
    selection_reason: str
    created_at: datetime
    updated_at: datetime


class AgentJobRead(ORMResponse):
    id: uuid.UUID
    thread_id: uuid.UUID
    goal: str
    source_kind: str | None
    source_external_id: str | None
    source_label: str | None
    source_metadata: dict[str, Any]
    scope_mode: str
    requested_scope: dict[str, Any]
    sources: list[AgentJobSourceRead]
    state: AgentJobState
    version: int
    safe_error_code: str | None
    safe_error_detail: str | None
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[AgentStepRead]
    created_at: datetime
    updated_at: datetime


class EvidenceRead(Schema):
    id: str
    source_kind: str
    source_id: str
    sender_display_name: str
    sent_at: datetime
    excerpt: str
    conversation_id: str


class ActionProposalCreate(Schema):
    action: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    destination: dict[str, Any]
    body: str = Field(min_length=1, max_length=8000)
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class ActionProposalRevise(Schema):
    body: str = Field(min_length=1, max_length=8000)
    reason: str | None = Field(default=None, max_length=4000)


class ApprovalDecisionCreate(Schema):
    decision: ApprovalDecisionType
    expected_revision: int = Field(ge=1)
    expected_payload_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalDecisionRead(ORMResponse):
    id: uuid.UUID
    proposal_id: uuid.UUID
    decision: ApprovalDecisionType
    proposal_revision: int
    payload_hash: str
    manager_identity: str
    reason: str | None
    decided_at: datetime


class ActionProposalRead(ORMResponse):
    id: uuid.UUID
    job_id: uuid.UUID
    plan_id: uuid.UUID | None
    sequence: int
    depends_on_logical_action_ids: list[str]
    logical_action_id: uuid.UUID
    previous_revision_id: uuid.UUID | None
    revision: int
    action: str
    state: ActionProposalState
    destination: dict[str, Any]
    body: str
    reason: str
    evidence_ids: list[str]
    payload_hash: str
    version: int
    expires_at: datetime | None
    approval: ApprovalDecisionRead | None
    created_at: datetime
    updated_at: datetime


class ToolExecutionRead(ORMResponse):
    id: uuid.UUID
    job_id: uuid.UUID
    proposal_id: uuid.UUID | None
    tool_name: str
    operation: str
    state: ToolExecutionState
    idempotency_key: str
    request_hash: str | None
    safe_result: dict[str, Any] | None
    safe_error_code: str | None
    safe_error_detail: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlannedActionRead(Schema):
    proposal: ActionProposalRead
    execution: ToolExecutionRead | None = None


class AgentActionPlanRead(ORMResponse):
    id: uuid.UUID
    job_id: uuid.UUID
    summary: str
    state: str
    plan_metadata: dict[str, Any]
    actions: list[PlannedActionRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BulkApprovalItem(Schema):
    proposal_id: uuid.UUID
    expected_revision: int = Field(ge=1)
    expected_payload_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class BulkApprovalCreate(Schema):
    items: list[BulkApprovalItem] = Field(min_length=1, max_length=12)


class AgentFoundationRead(Schema):
    enabled: bool
    threads: int = Field(ge=0)
    jobs: int = Field(ge=0)
    pending_approvals: int = Field(ge=0)
    executions: int = Field(ge=0)
    job_states: list[str]
    proposal_states: list[str]
