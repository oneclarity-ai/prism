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
from app.models.enums import PrismLifecycleState, PrismOnboardingStatus

if TYPE_CHECKING:
    from app.models.agent_v21 import AgentThread


class Prism(TimestampMixin, Base):
    """A private specialist agent owned by the single local Prism user."""

    __tablename__ = "prisms"
    __table_args__ = (
        Index(
            "uq_prisms_active_normalized_name",
            "normalized_name",
            unique=True,
            postgresql_where=text("state != 'ARCHIVED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False, default="blank")
    template_version: Mapped[Optional[str]] = mapped_column(String(80))
    state: Mapped[PrismLifecycleState] = mapped_column(
        Enum(PrismLifecycleState, name="prism_lifecycle_state"),
        nullable=False,
        default=PrismLifecycleState.DRAFT,
        index=True,
    )
    lifecycle_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agreement_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    lifecycle_events: Mapped[list["PrismLifecycleEvent"]] = relationship(
        "PrismLifecycleEvent",
        back_populates="prism",
        cascade="all, delete-orphan",
        order_by="PrismLifecycleEvent.sequence",
    )
    threads: Mapped[list["AgentThread"]] = relationship("AgentThread", back_populates="prism")
    agreements: Mapped[list["PrismWorkingAgreement"]] = relationship(
        "PrismWorkingAgreement",
        back_populates="prism",
        cascade="all, delete-orphan",
        order_by="PrismWorkingAgreement.revision",
    )
    trigger_policy: Mapped["PrismTriggerPolicy | None"] = relationship(
        "PrismTriggerPolicy", back_populates="prism", cascade="all, delete-orphan", uselist=False
    )
    runs: Mapped[list["PrismRun"]] = relationship(
        "PrismRun", back_populates="prism", cascade="all, delete-orphan"
    )
    observations: Mapped[list["PrismObservation"]] = relationship(
        "PrismObservation", back_populates="prism", cascade="all, delete-orphan"
    )


class PrismLifecycleEvent(TimestampMixin, Base):
    """Append-only explanation of a Prism lifecycle change."""

    __tablename__ = "prism_lifecycle_events"
    __table_args__ = (UniqueConstraint("prism_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_state: Mapped[Optional[PrismLifecycleState]] = mapped_column(
        Enum(PrismLifecycleState, name="prism_lifecycle_state")
    )
    target_state: Mapped[PrismLifecycleState] = mapped_column(
        Enum(PrismLifecycleState, name="prism_lifecycle_state"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(80), nullable=False, default="local_manager")
    reason: Mapped[Optional[str]] = mapped_column(Text)

    prism: Mapped[Prism] = relationship("Prism", back_populates="lifecycle_events")


class PrismOnboardingSession(TimestampMixin, Base):
    """Server-owned, resumable onboarding state for one private Prism."""

    __tablename__ = "prism_onboarding_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[PrismOnboardingStatus] = mapped_column(
        Enum(PrismOnboardingStatus, name="prism_onboarding_status"),
        nullable=False,
        default=PrismOnboardingStatus.IN_PROGRESS,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    question_set_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="fallback-v1"
    )
    generation_note: Mapped[str | None] = mapped_column(String(160))

    prism: Mapped["Prism"] = relationship("Prism")
    questions: Mapped[list["PrismOnboardingQuestion"]] = relationship(
        "PrismOnboardingQuestion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PrismOnboardingQuestion.position",
    )
    answers: Mapped[list["PrismOnboardingAnswer"]] = relationship(
        "PrismOnboardingAnswer", back_populates="session", cascade="all, delete-orphan"
    )


class PrismOnboardingQuestion(TimestampMixin, Base):
    """A display-safe, validated question. Prompt text never executes in the browser."""

    __tablename__ = "prism_onboarding_questions"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "position", name="uq_prism_onboarding_questions_session_position"
        ),
        UniqueConstraint("session_id", "key", name="uq_prism_onboarding_questions_session_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(40), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allows_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    choices: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    session: Mapped["PrismOnboardingSession"] = relationship(
        "PrismOnboardingSession", back_populates="questions"
    )
    answers: Mapped[list["PrismOnboardingAnswer"]] = relationship(
        "PrismOnboardingAnswer", back_populates="question", cascade="all, delete-orphan"
    )


class PrismOnboardingAnswer(TimestampMixin, Base):
    """The current, explicit manager answer—not hidden model reasoning."""

    __tablename__ = "prism_onboarding_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_onboarding_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_onboarding_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_values: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    custom_text: Mapped[str | None] = mapped_column(Text)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    session: Mapped["PrismOnboardingSession"] = relationship(
        "PrismOnboardingSession", back_populates="answers"
    )
    question: Mapped["PrismOnboardingQuestion"] = relationship(
        "PrismOnboardingQuestion", back_populates="answers"
    )


class PrismWorkingAgreement(TimestampMixin, Base):
    """Immutable, manager-confirmed behavior contract for one Prism revision."""

    __tablename__ = "prism_working_agreements"
    __table_args__ = (UniqueConstraint("prism_id", "revision"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    onboarding_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_onboarding_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    template_version: Mapped[str | None] = mapped_column(String(80))
    agreement: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_answer_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    generation_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column()

    prism: Mapped["Prism"] = relationship("Prism", back_populates="agreements")
    onboarding_session: Mapped["PrismOnboardingSession"] = relationship("PrismOnboardingSession")


class PrismTeamsSourcePolicy(TimestampMixin, Base):
    """The durable Teams read boundary for one private Prism.

    Rules deliberately reference a Graph chat ID.  Labels and participants are
    only display metadata: Teams can rename a group or change membership
    without silently broadening the Prism's access.
    """

    __tablename__ = "prism_teams_source_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="all_chats")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    discovery_cursor_external_id: Mapped[str | None] = mapped_column(String(512))
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_discovery_error: Mapped[str | None] = mapped_column(Text)

    rules: Mapped[list["PrismTeamsSourceRule"]] = relationship(
        "PrismTeamsSourceRule",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PrismTeamsSourceRule.created_at",
    )


class PrismTeamsSourceRule(TimestampMixin, Base):
    """A stable include or exclusion in a Prism's Teams policy."""

    __tablename__ = "prism_teams_source_rules"
    __table_args__ = (UniqueConstraint("policy_id", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_teams_source_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_type: Mapped[str | None] = mapped_column(String(32))
    participants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    policy: Mapped["PrismTeamsSourcePolicy"] = relationship(
        "PrismTeamsSourcePolicy", back_populates="rules"
    )


class PrismTeamsSourceCursor(TimestampMixin, Base):
    """A per-Prism, per-chat cursor for bounded local incremental polling."""

    __tablename__ = "prism_teams_source_cursors"
    __table_args__ = (UniqueConstraint("prism_id", "source_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(255))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_id: Mapped[str | None] = mapped_column(String(512))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="idle")
    last_error: Mapped[str | None] = mapped_column(Text)


class PrismExternalEvent(TimestampMixin, Base):
    """Normalized Teams activity with an idempotency key shared by pollers."""

    __tablename__ = "prism_external_events"
    __table_args__ = (
        UniqueConstraint("prism_id", "dedupe_key"),
        Index(
            "ix_prism_external_events_prism_source_occurred",
            "prism_id",
            "source_external_id",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    microsoft_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(255))
    external_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sender_external_id: Mapped[str | None] = mapped_column(String(512))
    sender_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reply_to_external_id: Mapped[str | None] = mapped_column(String(512))
    event_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class PrismTriggerPolicy(TimestampMixin, Base):
    """When a Prism may create a bounded monitoring run.

    This deliberately controls monitoring only. No policy in this table grants
    permission to message anyone; approval-gated actions remain a later phase.
    """

    __tablename__ = "prism_trigger_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    daily_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    missed_run_policy: Mapped[str] = mapped_column(String(24), nullable=False, default="run_once")
    continuous_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    event_coalesce_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    event_cursor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prism: Mapped["Prism"] = relationship("Prism", back_populates="trigger_policy")
    runs: Mapped[list["PrismRun"]] = relationship(
        "PrismRun", back_populates="trigger_policy", cascade="all, delete-orphan"
    )


class PrismRun(TimestampMixin, Base):
    """Durable, lease-claimed monitoring work; it does not perform an action."""

    __tablename__ = "prism_runs"
    __table_args__ = (
        UniqueConstraint("prism_id", "occurrence_key"),
        Index("ix_prism_runs_state_lease", "state", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_trigger_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_jobs.id", ondelete="SET NULL"), index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurrence_key: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    agreement_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_policy_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    budget: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prism: Mapped["Prism"] = relationship("Prism", back_populates="runs")
    trigger_policy: Mapped["PrismTriggerPolicy"] = relationship(
        "PrismTriggerPolicy", back_populates="runs"
    )


class PrismObservation(TimestampMixin, Base):
    """An evidence-linked proactive recommendation; it has no action authority."""

    __tablename__ = "prism_observations"
    __table_args__ = (
        UniqueConstraint("prism_id", "fingerprint"),
        Index("ix_prism_observations_prism_state_created", "prism_id", "state", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prism_runs.id", ondelete="SET NULL"), index=True
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    verified_facts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    inference: Mapped[str | None] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_next_step: Mapped[str] = mapped_column(Text, nullable=False)
    unknowns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_event_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prism_incidents.id", ondelete="SET NULL"), index=True
    )
    evidence_key: Mapped[str | None] = mapped_column(String(64), index=True)

    prism: Mapped["Prism"] = relationship("Prism", back_populates="observations")


class PrismNotificationSetting(TimestampMixin, Base):
    """Per-Prism browser notification preference; off until the user opts in."""

    __tablename__ = "prism_notification_settings"

    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_urgency: Mapped[str] = mapped_column(String(16), nullable=False, default="high")


class PrismNotification(TimestampMixin, Base):
    """One browser-delivery attempt for one durable observation (never the record itself)."""

    __tablename__ = "prism_notifications"
    __table_args__ = (
        UniqueConstraint("observation_id"),
        Index("ix_prism_notifications_state_created", "state", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    claimed_by: Mapped[str | None] = mapped_column(String(64))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(String(32))


class PrismPresence(Base):
    """A heartbeat from one open browser page; notifications are only claimed while fresh."""

    __tablename__ = "prism_presence"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrismIncident(TimestampMixin, Base):
    """A conservative link between observations about one Teams event; never merges Prism memory."""

    __tablename__ = "prism_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrismIncidentEvent(Base):
    """Append-only audit of why observations were grouped, evolved, resolved, or split."""

    __tablename__ = "prism_incident_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prism_observations.id", ondelete="SET NULL")
    )
    prism_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrismObservationDraft(Base):
    """Provenance for a Teams draft prepared from an observation; it carries no approval authority."""

    __tablename__ = "prism_observation_drafts"
    __table_args__ = (UniqueConstraint("observation_id", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agreement_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_event_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_reason: Mapped[str | None] = mapped_column(String(120))


class PrismObservationFeedback(Base):
    """User judgment about one observation; scoped to its Prism and never shared."""

    __tablename__ = "prism_observation_feedback"
    __table_args__ = (UniqueConstraint("observation_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prism_observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrismSignalPreference(TimestampMixin, Base):
    """An explicit, user-confirmed per-Prism signal choice (learning only ever suggests)."""

    __tablename__ = "prism_signal_preferences"

    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), primary_key=True
    )
    signal_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppressed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrismBudget(TimestampMixin, Base):
    """Per-Prism operational limits; null means use the safe global default."""

    __tablename__ = "prism_budgets"

    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), primary_key=True
    )
    max_runs_per_day: Mapped[int | None] = mapped_column(Integer)
    max_model_calls_per_day: Mapped[int | None] = mapped_column(Integer)
    max_consecutive_failures: Mapped[int | None] = mapped_column(Integer)
