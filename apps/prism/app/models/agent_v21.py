from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ActionProposalState,
    AgentJobState,
    AgentStepState,
    ApprovalDecisionType,
    ToolExecutionState,
)

if TYPE_CHECKING:
    from app.models.prism_v22 import Prism


class AgentThread(TimestampMixin, Base):
    __tablename__ = "agent_threads"
    __table_args__ = (
        Index(
            "uq_agent_threads_one_legacy_canonical",
            "is_canonical",
            unique=True,
            postgresql_where=text("is_canonical AND prism_id IS NULL"),
        ),
        Index(
            "uq_agent_threads_one_prism_canonical",
            "prism_id",
            unique=True,
            postgresql_where=text("is_canonical AND prism_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_kind: Mapped[Optional[str]] = mapped_column(String(40))
    source_external_id: Mapped[Optional[str]] = mapped_column(String(512), index=True)
    source_label: Mapped[Optional[str]] = mapped_column(String(255))
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )

    prism: Mapped[Optional["Prism"]] = relationship("Prism", back_populates="threads")

    jobs: Mapped[list["AgentJob"]] = relationship(
        "AgentJob", back_populates="thread", cascade="all, delete-orphan"
    )
    messages: Mapped[list["AgentThreadMessage"]] = relationship(
        "AgentThreadMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgentThreadMessage.created_at",
    )


class AgentThreadAlias(TimestampMixin, Base):
    __tablename__ = "agent_thread_aliases"

    legacy_thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    canonical_thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True
    )


class AgentThreadMessage(TimestampMixin, Base):
    __tablename__ = "agent_thread_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    thread: Mapped[AgentThread] = relationship("AgentThread", back_populates="messages")


class AgentJob(TimestampMixin, Base):
    __tablename__ = "agent_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[Optional[str]] = mapped_column(String(40))
    source_external_id: Mapped[Optional[str]] = mapped_column(String(512), index=True)
    source_label: Mapped[Optional[str]] = mapped_column(String(255))
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scope_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="chat", index=True)
    requested_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[AgentJobState] = mapped_column(
        Enum(AgentJobState, name="agent_job_state"),
        nullable=False,
        default=AgentJobState.QUEUED,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    safe_error_code: Mapped[Optional[str]] = mapped_column(String(80))
    safe_error_detail: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    thread: Mapped[AgentThread] = relationship("AgentThread", back_populates="jobs")
    steps: Mapped[list["AgentStep"]] = relationship(
        "AgentStep",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="AgentStep.sequence",
    )
    proposals: Mapped[list["ActionProposal"]] = relationship(
        "ActionProposal", back_populates="job", cascade="all, delete-orphan"
    )
    executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution", back_populates="job", cascade="all, delete-orphan"
    )
    source_messages: Mapped[list["AgentSourceMessage"]] = relationship(
        "AgentSourceMessage", back_populates="job", cascade="all, delete-orphan"
    )
    sources: Mapped[list["AgentJobSource"]] = relationship(
        "AgentJobSource", back_populates="job", cascade="all, delete-orphan"
    )
    review: Mapped[Optional["AgentConversationReview"]] = relationship(
        "AgentConversationReview", back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    action_plan: Mapped[Optional["AgentActionPlan"]] = relationship(
        "AgentActionPlan", back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class AgentJobSource(TimestampMixin, Base):
    __tablename__ = "agent_job_sources"
    __table_args__ = (UniqueConstraint("job_id", "source_kind", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    selection_reason: Mapped[str] = mapped_column(String(80), nullable=False, default="explicit")

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="sources")


class AgentSourceMessage(TimestampMixin, Base):
    __tablename__ = "agent_source_messages"
    __table_args__ = (
        UniqueConstraint("job_id", "external_conversation_id", "external_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    external_conversation_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    external_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    sender_external_id: Mapped[Optional[str]] = mapped_column(String(512))
    sender_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    quoted_text: Mapped[Optional[str]] = mapped_column(Text)
    reply_to_external_id: Mapped[Optional[str]] = mapped_column(String(512))
    message_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="source_messages")


class AgentConversationReview(TimestampMixin, Base):
    __tablename__ = "agent_conversation_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    attention_items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    manager_questions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    requires_reply: Mapped[bool] = mapped_column(nullable=False)
    proposed_reply: Mapped[Optional[dict]] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    applied_preference_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="review")


class AgentPreference(TimestampMixin, Base):
    __tablename__ = "agent_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # A v2.2 preference belongs to exactly one private Prism.  Legacy v2.1
    # preferences deliberately remain NULL so existing conversations retain
    # their behaviour without becoming visible to a new Prism by accident.
    prism_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), index=True
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="general", index=True)
    source_kind: Mapped[str] = mapped_column(String(60), nullable=False)
    source_thread_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)


class AgentFeedbackEvent(TimestampMixin, Base):
    __tablename__ = "agent_feedback_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="SET NULL"), index=True
    )
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_executions.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AgentStep(TimestampMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[AgentStepState] = mapped_column(
        Enum(AgentStepState, name="agent_step_state"),
        nullable=False,
        default=AgentStepState.QUEUED,
    )
    safe_error_code: Mapped[Optional[str]] = mapped_column(String(80))
    safe_error_detail: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="steps")


class AgentActionPlan(TimestampMixin, Base):
    __tablename__ = "agent_action_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending", server_default="pending", index=True
    )
    plan_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="action_plan")
    proposals: Mapped[list["ActionProposal"]] = relationship(
        "ActionProposal", back_populates="plan"
    )


class ActionProposal(TimestampMixin, Base):
    __tablename__ = "action_proposals"
    __table_args__ = (UniqueConstraint("logical_action_id", "revision"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_action_plans.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    depends_on_logical_action_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    logical_action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    previous_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[ActionProposalState] = mapped_column(
        Enum(ActionProposalState, name="action_proposal_state"),
        nullable=False,
        default=ActionProposalState.DRAFT,
        index=True,
    )
    destination: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    payload_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="proposals")
    plan: Mapped[Optional[AgentActionPlan]] = relationship(
        "AgentActionPlan", back_populates="proposals"
    )
    previous_revision: Mapped[Optional["ActionProposal"]] = relationship(
        "ActionProposal", remote_side=[id]
    )
    approval: Mapped[Optional["ApprovalDecision"]] = relationship(
        "ApprovalDecision", back_populates="proposal", uselist=False, cascade="all, delete-orphan"
    )
    executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution", back_populates="proposal"
    )


class ApprovalDecision(TimestampMixin, Base):
    __tablename__ = "approval_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_proposals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    decision: Mapped[ApprovalDecisionType] = mapped_column(
        Enum(ApprovalDecisionType, name="approval_decision_type"), nullable=False
    )
    proposal_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    manager_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    proposal: Mapped[ActionProposal] = relationship("ActionProposal", back_populates="approval")


class ToolExecution(TimestampMixin, Base):
    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[ToolExecutionState] = mapped_column(
        Enum(ToolExecutionState, name="tool_execution_state"),
        nullable=False,
        default=ToolExecutionState.PENDING,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(71))
    safe_result: Mapped[Optional[dict]] = mapped_column(JSONB)
    safe_error_code: Mapped[Optional[str]] = mapped_column(String(80))
    safe_error_detail: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job: Mapped[AgentJob] = relationship("AgentJob", back_populates="executions")
    proposal: Mapped[Optional[ActionProposal]] = relationship(
        "ActionProposal", back_populates="executions"
    )
