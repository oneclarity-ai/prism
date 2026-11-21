import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import ApprovalStatus, BugStatus, RunKind, RunStatus, RunTrigger, Severity, TestCaseStatus
from app.schemas.common import ORMModel


class RunStart(BaseModel):
    """Choices for one run. Everything is optional: an empty body runs the whole task with one agent."""

    mode: Literal["single", "parallel"] = "single"
    pages: list[str] | None = Field(default=None, description="Test only these pages (default: all task pages)")
    max_parallel: int | None = Field(default=None, ge=1, le=8, description="Parallel: sub-agents working at once")
    pages_per_agent: int = Field(default=1, ge=1, le=10, description="Parallel: pages given to each sub-agent")
    max_turns: int | None = Field(default=None, ge=5, le=300, description="Per agent; default from the agent")
    budget_usd: float | None = Field(default=None, gt=0, le=50, description="Per agent; default from the agent")
    operation_key: str | None = Field(default=None, min_length=8, max_length=200)


class RunRead(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    trigger: RunTrigger
    runtime: str | None = None
    model: str | None = None
    status: RunStatus
    resumes_run_id: uuid.UUID | None
    resumed_by_run_id: uuid.UUID | None = None
    kind: RunKind = RunKind.single
    # Parallel runs: totals including every sub-agent (cost_usd / tokens above are the merge only).
    total_cost_usd: Decimal | None = None
    total_tokens: int | None = None
    parent_run_id: uuid.UUID | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    cancel_requested: bool
    started_at: datetime | None
    ended_at: datetime | None
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cost_usd: Decimal
    summary: str
    result: dict[str, Any] | None = None
    error: str | None
    attempt: int = 0
    checkpoint_at: datetime | None = None
    active_tool: str | None = None
    created_at: datetime
    task_title: str | None = None
    agent_name: str | None = None


class SubAgentRead(BaseModel):
    """One lane of a parallel run: a sub-agent, its pages and what it is doing right now."""

    index: int
    label: str
    pages: list[str]
    task_id: uuid.UUID
    run_id: uuid.UUID  # latest run of this sub-agent (a follow-up run after an approval)
    status: RunStatus
    started_at: datetime | None
    ended_at: datetime | None
    error: str | None
    summary: str
    turn: int | None = None
    max_turns: int | None = None
    cost_usd: float = 0.0
    budget_usd: float | None = None
    tokens: int = 0
    activity: str | None = None  # e.g. "browser_click: Book a demo"
    activity_at: datetime | None = None
    cases_total: int = 0
    cases_pass: int = 0
    cases_fail: int = 0
    cases_blocked: int = 0
    bugs: int = 0


class RunEventRead(ORMModel):
    seq: int
    type: str  # message | tool_call | tool_result | status | log | usage | artifact
    payload: dict[str, Any]
    created_at: datetime


class TestCaseRead(ORMModel):
    __test__ = False

    id: uuid.UUID
    run_id: uuid.UUID
    title: str
    given: str
    when: str
    then: str
    status: TestCaseStatus
    evidence_artifact_ids: list[uuid.UUID]
    notes: str
    updated_at: datetime


class BugRead(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    test_case_id: uuid.UUID | None
    title: str
    steps: str
    expected: str
    actual: str
    severity: Severity
    status: BugStatus
    external_url: str | None
    duplicate_of_id: uuid.UUID | None = None
    created_at: datetime


class ArtifactRead(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    kind: str
    mime: str
    meta: dict[str, Any]
    created_at: datetime


class ApprovalRead(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    action: str
    payload: dict[str, Any]
    status: ApprovalStatus
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    comment: str
    created_at: datetime
    task_id: uuid.UUID | None = None
    task_title: str | None = None


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=2000)
    # Extra input for the paused tool: {"answer": "..."} for ask_manager. Never put secrets here.
    payload: dict[str, str] | None = None
    operation_key: str | None = Field(default=None, min_length=8, max_length=200)


class ApprovalDecisionResult(BaseModel):
    approval: ApprovalRead
    resume_run_id: uuid.UUID | None


class UsageRow(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    monthly_budget_usd: Decimal
    month_spend_usd: Decimal
    runs: int
    input_tokens: int
    output_tokens: int
    total_cost_usd: Decimal


class RuntimeStatus(BaseModel):
    workers_online: int
    azure_configured: bool
    deployment: str
    runtimes: list[str]
