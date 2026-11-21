import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.enums import RunKind, RunStatus, RunTrigger


class Run(IdMixin, TimestampMixin, Base):
    """One heartbeat: a bounded execution of an agent on a task."""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_status_created", "status", "created_at"),
        UniqueConstraint("org_id", "operation_key", name="uq_runs_org_operation_key"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"))
    trigger: Mapped[str] = mapped_column(String(32), default=RunTrigger.manual)
    runtime: Mapped[str | None] = mapped_column(String(64))  # set when the run starts
    model: Mapped[str | None] = mapped_column(String(200))  # Azure deployment used, e.g. gpt-5-mini
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.queued)
    resumes_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32), default=RunKind.single, server_default=RunKind.single)
    # Parallel runs: each sub-agent run points at the orchestrator run.
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    # Per-run choices: pages, max_turns, budget_usd; parallel: max_parallel, pages_per_agent, label, phase.
    options: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Serialized SDK run state, saved when the run stops for approval.
    saved_state: Mapped[dict | None] = mapped_column(JSONB)
    lease_owner: Mapped[str | None] = mapped_column(String(200), index=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt: Mapped[int] = mapped_column(default=0, server_default="0")
    checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_tool: Mapped[str | None] = mapped_column(String(120))
    active_tool_risky: Mapped[bool] = mapped_column(default=False, server_default="false")
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    # Part of input_tokens that Azure billed at the cheaper cached rate.
    cached_input_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), default=Decimal("0"))
    summary: Mapped[str] = mapped_column(Text, default="")
    # What a generic task produced: {"outcome", "results": [{...}], "files": [{"name", "artifact_id"}]}.
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    operation_key: Mapped[str | None] = mapped_column(String(200))


class RunEvent(Base):
    """Append-only live log of a run, streamed to the UI."""

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    seq: Mapped[int]
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(2000))
    mime: Mapped[str] = mapped_column(String(200), default="application/octet-stream")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
