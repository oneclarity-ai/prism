from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import AgentAnalysisType, AgentRunStatus

if TYPE_CHECKING:
    from app.models.blocker import Blocker
    from app.models.employee import Employee
    from app.models.message import Message


class AgentRun(TimestampMixin, Base):
    """Auditable result of analysing one inbound Teams message."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inbound_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    source_employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status"),
        nullable=False,
        default=AgentRunStatus.PENDING,
        index=True,
    )
    analysis_type: Mapped[Optional[AgentAnalysisType]] = mapped_column(
        Enum(AgentAnalysisType, name="agent_analysis_type"), index=True
    )
    model_deployment: Mapped[Optional[str]] = mapped_column(String(255))
    completed_summary: Mapped[Optional[str]] = mapped_column(Text)
    today_summary: Mapped[Optional[str]] = mapped_column(Text)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    blocker_description: Mapped[Optional[str]] = mapped_column(Text)
    dependency_owner_name: Mapped[Optional[str]] = mapped_column(String(255))
    dependency_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blockers.id", ondelete="SET NULL"), index=True
    )
    source_reply_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    dependency_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    eta_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    commitment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commitments.id", ondelete="SET NULL"), index=True
    )
    needs_yash_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    decision_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    context_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    state_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    policy_version: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    inbound_message: Mapped["Message"] = relationship("Message", foreign_keys=[inbound_message_id])
    source_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[source_employee_id])
    dependency_owner: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[dependency_owner_id]
    )
    blocker: Mapped[Optional["Blocker"]] = relationship("Blocker")
    source_reply_message: Mapped[Optional["Message"]] = relationship(
        "Message", foreign_keys=[source_reply_message_id]
    )
    dependency_message: Mapped[Optional["Message"]] = relationship(
        "Message", foreign_keys=[dependency_message_id]
    )
    commitment: Mapped[Optional["Commitment"]] = relationship("Commitment")
