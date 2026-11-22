"""Public contracts for the Prism v2.2 workspace."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.enums import PrismLifecycleState, PrismOnboardingStatus
from app.schemas.common import ORMResponse, Schema
from app.schemas.prisms.agent_v21 import (
    AgentJobRead,
    AgentPreferenceRead,
    AgentThreadMessageRead,
    AgentThreadRead,
)


class PrismFoundationRead(Schema):
    """Safe, feature-gated description of the currently available v2.2 surface."""

    enabled: bool
    release: Literal["v2.2"]
    phase: int
    single_executive_mode: bool
    capabilities: list[str]
    excluded_capabilities: list[str]


PrismColor = Literal["red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]


ToolGrant = Literal["allowed", "ask_first", "off"]


class PrismCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=8000)
    job_role: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    reports_to_prism_id: uuid.UUID | None = None
    template_key: Literal["blank", "executive_assistant", "qa_tester"] = "blank"
    template_version: str | None = Field(default=None, max_length=80)
    color: PrismColor | None = None
    # v2.4: what the Prism may use (browsing is always on) and whether it may sign in to sites.
    capabilities: list[Literal["files", "teams"]] | None = None
    logins_policy: Literal["never", "ask"] = "never"
    role_instructions: str | None = Field(default=None, max_length=6000)
    # True: the Prism is ready to chat and work straight away (no onboarding questions).
    activate: bool = False


class PrismProfileUpdate(Schema):
    capabilities: list[Literal["files", "teams"]] | None = None
    logins_policy: Literal["never", "ask"] | None = None
    role_instructions: str | None = Field(default=None, max_length=6000)
    tool_grants: dict[str, ToolGrant] | None = None
    max_turns: int | None = Field(default=None, ge=5, le=300)
    run_budget_usd: float | None = Field(default=None, gt=0, le=50)
    monthly_budget_usd: float | None = Field(default=None, gt=0, le=100000)


class PrismUpdate(Schema):
    expected_lifecycle_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=8000)
    color: PrismColor | None = None
    job_role: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    reports_to_prism_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def has_change(self) -> "PrismUpdate":
        if (
            self.name is None
            and self.description is None
            and self.color is None
            and self.job_role is None
            and self.department is None
            and "reports_to_prism_id" not in self.model_fields_set
        ):
            raise ValueError("Provide a name, description, or colour to update a Prism")
        return self


class PrismLifecycleCommand(Schema):
    expected_lifecycle_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class PrismRead(ORMResponse):
    id: uuid.UUID
    code: str | None = None
    name: str
    description: str
    job_role: str = "Prism Specialist"
    department: str = "Operations"
    reports_to_prism_id: uuid.UUID | None = None
    is_chief_of_staff: bool = False
    template_key: str
    template_version: str | None
    color: str | None = None
    capabilities: list[str] = ["browser"]
    logins_policy: str = "never"
    role_instructions: str | None = None
    tool_grants: dict[str, str] | None = None
    max_turns: int | None = None
    run_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    tools_allowed: int = 0
    tools_ask_first: int = 0
    state: PrismLifecycleState
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    last_message_role: str | None = None
    last_message_preview: str | None = None


class PrismDescriptionRequest(Schema):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    department: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=6000)


class PrismDescriptionRead(Schema):
    description: str


class PrismToolRead(Schema):
    name: str
    label: str
    description: str
    group: str
    grant: ToolGrant


class PrismToolsRead(Schema):
    tools: list[PrismToolRead]


class PrismOrganizationRead(Schema):
    owner_name: str
    chief_of_staff_id: uuid.UUID | None
    departments: list[str]
    members: list[PrismRead]


class PrismSearchResultRead(Schema):
    kind: Literal["prism", "message"]
    prism_id: uuid.UUID
    prism_name: str
    message_id: uuid.UUID | None
    role: str | None
    created_at: datetime | None
    snippet: str


class PrismLifecycleEventRead(ORMResponse):
    id: uuid.UUID
    prism_id: uuid.UUID
    sequence: int
    event_type: str
    previous_state: PrismLifecycleState | None
    target_state: PrismLifecycleState
    actor: str
    reason: str | None
    created_at: datetime


class PrismOnboardingChoice(Schema):
    value: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)


class PrismOnboardingQuestionRead(ORMResponse):
    id: uuid.UUID
    key: str
    position: int
    prompt: str
    help_text: str | None
    question_type: Literal["single_choice", "multiple_choice", "short_text", "long_text"]
    required: bool
    allows_custom: bool
    choices: list[PrismOnboardingChoice]


class PrismOnboardingAnswerRead(ORMResponse):
    question_id: uuid.UUID
    selected_values: list[str]
    custom_text: str | None
    skipped: bool


class PrismOnboardingSessionRead(ORMResponse):
    id: uuid.UUID
    prism_id: uuid.UUID
    status: PrismOnboardingStatus
    revision: int
    question_set_version: str
    generation_note: str | None
    questions: list[PrismOnboardingQuestionRead]
    answers: list[PrismOnboardingAnswerRead]
    current_question_id: uuid.UUID | None


class PrismOnboardingAnswerInput(Schema):
    expected_revision: int = Field(ge=1)
    selected_values: list[str] = Field(default_factory=list, max_length=12)
    custom_text: str | None = Field(default=None, max_length=2000)
    skipped: bool = False


class PrismAgreementRead(ORMResponse):
    id: uuid.UUID
    prism_id: uuid.UUID
    revision: int
    status: Literal["draft", "confirmed", "superseded"]
    template_key: str
    template_version: str | None
    agreement: dict
    source_answer_ids: list[uuid.UUID]
    generation_metadata: dict
    confirmed_at: datetime | None
    created_at: datetime


class PrismAgreementConfirm(Schema):
    expected_agreement_revision: int = Field(ge=1)
    expected_lifecycle_version: int = Field(ge=1)


class PrismAgreementConfirmationRead(Schema):
    agreement: PrismAgreementRead
    prism: PrismRead
    skills_created: int = 0
    skills_error: str | None = None


class PrismConversationRead(Schema):
    prism_id: uuid.UUID
    thread: AgentThreadRead
    messages: list[AgentThreadMessageRead]
    jobs: list[AgentJobRead]
    preferences: list[AgentPreferenceRead]


class PrismMemoryCreate(Schema):
    instruction: str = Field(min_length=3, max_length=4000)


class PrismTeamsSourceRuleRead(ORMResponse):
    external_id: str
    disposition: Literal["include", "exclude"]
    label: str
    chat_type: str | None
    participants: list[str]


class PrismTeamsSourcePolicyRead(ORMResponse):
    prism_id: uuid.UUID
    mode: Literal["all_chats", "include_only", "all_except"]
    revision: int
    rules: list[PrismTeamsSourceRuleRead]
    last_discovery_at: datetime | None
    last_discovery_error: str | None


class PrismTeamsSourcePolicyUpdate(Schema):
    expected_revision: int = Field(ge=1)
    mode: Literal["all_chats", "include_only", "all_except"]
    external_ids: list[str] = Field(default_factory=list, max_length=250)


class PrismTeamsEventRead(ORMResponse):
    id: uuid.UUID
    source_external_id: str
    source_label: str | None
    external_message_id: str
    event_kind: Literal["created", "updated", "deleted"]
    occurred_at: datetime
    sender_display_name: str
    body_text: str
    event_metadata: dict


class PrismTeamsEventsPage(Schema):
    items: list[PrismTeamsEventRead]
    total: int = Field(ge=0)


class PrismTeamsSyncRead(Schema):
    prism_id: uuid.UUID
    scanned_chats: int = Field(ge=0)
    fetched_messages: int = Field(ge=0)
    created_events: int = Field(ge=0)
    duplicate_events: int = Field(ge=0)
    source_errors: list[dict[str, str]] = Field(default_factory=list)
    status: Literal["ok", "degraded"]
    next_discovery_cursor: str | None
    last_discovery_at: datetime | None


class PrismTriggerPolicyRead(ORMResponse):
    prism_id: uuid.UUID
    mode: Literal["manual", "scheduled", "event_driven", "continuous"]
    revision: int
    enabled: bool
    timezone: str
    daily_time: str
    missed_run_policy: Literal["run_once", "skip"]
    continuous_interval_seconds: int
    event_coalesce_seconds: int
    event_cursor_at: datetime | None
    last_scheduled_for: datetime | None
    next_scheduled_for: datetime | None = None
    local_scheduler_enabled: bool


class PrismTriggerPolicyUpdate(Schema):
    expected_revision: int = Field(ge=1)
    mode: Literal["manual", "scheduled", "event_driven", "continuous"]
    enabled: bool = True
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    daily_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    missed_run_policy: Literal["run_once", "skip"] = "run_once"
    continuous_interval_seconds: int = Field(default=300, ge=60, le=86400)
    event_coalesce_seconds: int = Field(default=180, ge=30, le=86400)


class PrismRunRead(ORMResponse):
    id: uuid.UUID
    prism_id: uuid.UUID
    trigger_type: Literal["manual", "scheduled", "event_driven", "continuous"]
    occurrence_key: str
    state: Literal["queued", "running", "completed", "skipped", "failed", "cancelled"]
    agreement_revision: int
    source_policy_revision: int
    budget: dict
    input_event_count: int
    attempt_count: int
    scheduled_for: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    safe_error: str | None
    result: dict
    created_at: datetime
    updated_at: datetime


class PrismRunPage(Schema):
    items: list[PrismRunRead]
    total: int = Field(ge=0)


class PrismObservationRead(ORMResponse):
    id: uuid.UUID
    prism_id: uuid.UUID
    run_id: uuid.UUID | None
    state: Literal["open", "resolved", "superseded"]
    signal_type: Literal[
        "production_incident",
        "missed_deadline",
        "blocker",
        "unanswered_message",
        "customer_discussion",
    ]
    urgency: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    summary: str
    verified_facts: list[str]
    inference: str | None
    why_it_matters: str
    suggested_next_step: str
    unknowns: list[str]
    evidence_event_ids: list[uuid.UUID]
    source_external_id: str
    source_label: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    read_at: datetime | None = None
    incident_id: uuid.UUID | None = None
    feedback_kinds: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PrismObservationPage(Schema):
    items: list[PrismObservationRead]
    total: int = Field(ge=0)


Urgency = Literal["low", "medium", "high", "critical"]


class PrismUpdateSummaryRead(Schema):
    """Durable unread counters for one Prism, derived from stored observations."""

    prism_id: uuid.UUID
    unread: int = Field(ge=0)
    urgent_unread: int = Field(ge=0)
    latest_unread_at: datetime | None = None


class PrismObservationsRead(Schema):
    observation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class PrismNotificationSettingRead(ORMResponse):
    prism_id: uuid.UUID
    enabled: bool
    min_urgency: Urgency


class PrismNotificationSettingUpdate(Schema):
    enabled: bool
    min_urgency: Urgency = "high"


class PrismPresenceBeat(Schema):
    client_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PrismNotificationClaim(Schema):
    """Minimal, sanitized content for the browser; never raw Teams evidence."""

    notification_id: uuid.UUID
    prism_id: uuid.UUID
    observation_id: uuid.UUID
    title: str
    body: str
    urgency: Urgency
    tag: str


class PrismNotificationClaimRead(Schema):
    notification: PrismNotificationClaim | None = None


class PrismNotificationResult(Schema):
    client_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    result: Literal["delivered", "denied", "unsupported", "error"]


class PrismIncidentEventRead(Schema):
    event_type: Literal["opened", "linked", "updated", "resolved", "reopened", "split"]
    reason: str
    created_at: datetime
    mine: bool
    observation_id: uuid.UUID | None = None


class PrismIncidentHistoryRead(Schema):
    """Why an observation was grouped; other Prisms appear only as an anonymous count."""

    incident_id: uuid.UUID | None
    state: Literal["open", "resolved"] | None
    other_prisms: int = Field(ge=0)
    events: list[PrismIncidentEventRead]


class PrismObservationDraftCreate(Schema):
    """Explicit drafting intent. The destination is always the chat where the signal was seen."""

    request_id: uuid.UUID
    instruction: str | None = Field(default=None, min_length=3, max_length=1000)


class PrismObservationDraftRead(ORMResponse):
    id: uuid.UUID
    observation_id: uuid.UUID
    job_id: uuid.UUID
    agreement_revision: int
    incident_id: uuid.UUID | None
    created_at: datetime
    invalidated_at: datetime | None
    invalidated_reason: str | None


class PrismFeedbackCreate(Schema):
    kind: Literal[
        "helpful",
        "not_helpful",
        "wrong_urgency",
        "wrong_evidence",
        "duplicate",
        "no_longer_relevant",
    ]


class PrismSignalMute(Schema):
    muted: bool


class PrismBudgetUpdate(Schema):
    """Per-Prism limits. Omitted or null keeps the safe global default."""

    max_runs_per_day: int | None = Field(default=None, ge=1, le=5000)
    max_model_calls_per_day: int | None = Field(default=None, ge=0, le=5000)
    max_consecutive_failures: int | None = Field(default=None, ge=1, le=20)
