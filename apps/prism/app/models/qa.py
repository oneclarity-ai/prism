from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

QA_ACTIVE_STATES = ("starting", "running", "waiting_approval")
QA_TERMINAL_STATES = ("succeeded", "failed", "cancelled", "timed_out", "error")


class QaRun(TimestampMixin, Base):
    """One website test a QA tester Prism runs on the hidden QA swarm."""

    __tablename__ = "qa_runs"
    __table_args__ = (Index("ix_qa_runs_state", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    # "qa": a website test (v2.3). "work": any task done on the Prism's own computer (v2.4).
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="qa", server_default="qa")
    checklist: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    latest_frame_id: Mapped[Optional[str]] = mapped_column(String(64))
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    swarm_target_id: Mapped[Optional[str]] = mapped_column(String(64))
    swarm_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    swarm_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    swarm_run_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_url: Mapped[Optional[str]] = mapped_column(String(2048))
    current_activity: Mapped[Optional[str]] = mapped_column(String(300))
    activity_log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    latest_screenshot_id: Mapped[Optional[str]] = mapped_column(String(64))
    screenshot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cases: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    turn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    report: Mapped[Optional[dict]] = mapped_column(JSONB)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class QaApproval(TimestampMixin, Base):
    """A bug-filing approval the swarm paused on, relayed to the manager in chat."""

    __tablename__ = "qa_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qa_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("qa_runs.id", ondelete="CASCADE"), index=True
    )
    swarm_approval_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    # bug_filing | outward_action | login | question
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="bug_filing", server_default="bug_filing"
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    comment: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
