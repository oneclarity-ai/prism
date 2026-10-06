from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, field_validator

from app.models.enums import (
    AgentRunStatus,
    AutomationActionStatus,
    AutomationStatus,
    MicrosoftSubscriptionStatus,
)
from app.schemas.common import ORMResponse, Schema


class MicrosoftConnectionRead(ORMResponse):
    id: uuid.UUID
    tenant_id: str
    microsoft_user_id: str
    user_principal_name: str
    display_name: str
    granted_scopes: str
    access_token_expires_at: datetime
    last_connected_at: datetime
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class DirectorySyncResult(Schema):
    created: int = Field(ge=0)
    updated: int = Field(ge=0)
    skipped: int = Field(ge=0)
    active_users_seen: int = Field(ge=0)


class AutomationStart(Schema):
    initial_prompt: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    target_employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)

    @field_validator("initial_prompt")
    @classmethod
    def normalize_prompt(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else None


class AutomationRunRead(ORMResponse):
    id: uuid.UUID
    connection_id: uuid.UUID
    status: AutomationStatus
    initial_prompt: str
    target_employee_ids: list[str]
    target_count: int
    delivered_count: int
    failed_count: int
    started_at: datetime
    stopped_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class MicrosoftStatusRead(Schema):
    is_auth_configured: bool
    is_configured: bool
    is_connected: bool
    connection: Optional[MicrosoftConnectionRead] = None
    active_run: Optional[AutomationRunRead] = None
    listener_expires_at: Optional[datetime] = None


class SubscriptionRenewalResult(Schema):
    renewed: int = Field(ge=0)
    failed: int = Field(ge=0)
    listener_expires_at: Optional[datetime] = None


class MicrosoftSubscriptionRead(ORMResponse):
    id: uuid.UUID
    conversation_id: uuid.UUID
    external_subscription_id: str
    expires_at: datetime
    status: MicrosoftSubscriptionStatus
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class DailyDigestRead(Schema):
    id: uuid.UUID
    digest_date: date
    status: AutomationActionStatus
    sent_at: datetime
    content: str


class AgentDecisionRunRead(Schema):
    id: uuid.UUID
    inbound_message_id: uuid.UUID
    source_employee_id: uuid.UUID
    status: AgentRunStatus
    model_deployment: Optional[str]
    state_applied: bool
    needs_yash_review: bool
    failure_reason: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime
    decision: Optional[dict]
    context_source_ids: list[str]
    context: Optional[dict]
    llm_calls: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    unpriced_calls: int
    latency_ms: int
    attempt_count: int
    last_attempt_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    policy_version: Optional[str]
