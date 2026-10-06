from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ActivityEventType,
    ManagementProcedureStatus,
    MemoryEpisodeType,
    MemoryFactStatus,
    MemoryJobStatus,
    MemoryPredicate,
    VisibilityScope,
)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_activity_events_idempotency_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[ActivityEventType] = mapped_column(
        Enum(ActivityEventType, name="activity_event_type"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    actor_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    subject_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    processing_status: Mapped[MemoryJobStatus] = mapped_column(
        Enum(MemoryJobStatus, name="memory_job_status"),
        default=MemoryJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemorySource(Base):
    __tablename__ = "memory_sources"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_memory_sources_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    activity_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_events.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryFact(TimestampMixin, Base):
    __tablename__ = "memory_facts"
    __table_args__ = (
        Index(
            "ix_memory_facts_full_text",
            text(
                "to_tsvector('simple'::regconfig, (COALESCE(subject_text, ''::text) || ' '::text) || COALESCE(object_text, ''::text))"
            ),
            postgresql_using="gin",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    subject_text: Mapped[Optional[str]] = mapped_column(Text)
    predicate: Mapped[MemoryPredicate] = mapped_column(
        Enum(MemoryPredicate, name="memory_predicate"), nullable=False, index=True
    )
    object_type: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    object_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    object_text: Mapped[Optional[str]] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[MemoryFactStatus] = mapped_column(
        Enum(MemoryFactStatus, name="memory_fact_status"),
        default=MemoryFactStatus.CURRENT,
        nullable=False,
        index=True,
    )
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(Integer, default=50, nullable=False, index=True)
    supersedes_fact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_facts.id", ondelete="SET NULL"), index=True
    )
    visibility_scope: Mapped[VisibilityScope] = mapped_column(
        Enum(VisibilityScope, name="visibility_scope"),
        default=VisibilityScope.MANAGER_ONLY,
        nullable=False,
        index=True,
    )
    extractor_version: Mapped[Optional[str]] = mapped_column(String(100))


class MemoryEpisode(TimestampMixin, Base):
    __tablename__ = "memory_episodes"
    __table_args__ = (
        Index(
            "ix_memory_episodes_full_text",
            text("to_tsvector('simple'::regconfig, (title::text || ' '::text) || summary)"),
            postgresql_using="gin",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    episode_type: Mapped[MemoryEpisodeType] = mapped_column(
        Enum(MemoryEpisodeType, name="memory_episode_type"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    importance: Mapped[int] = mapped_column(Integer, default=50, nullable=False, index=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    primary_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    visibility_scope: Mapped[VisibilityScope] = mapped_column(
        Enum(VisibilityScope, name="visibility_scope"),
        default=VisibilityScope.MANAGER_ONLY,
        nullable=False,
        index=True,
    )
    extractor_version: Mapped[Optional[str]] = mapped_column(String(100))


class MemoryRelation(TimestampMixin, Base):
    __tablename__ = "memory_relations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    relation_type: Mapped[MemoryPredicate] = mapped_column(
        Enum(MemoryPredicate, name="memory_predicate"), nullable=False, index=True
    )
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[MemoryFactStatus] = mapped_column(
        Enum(MemoryFactStatus, name="memory_fact_status"),
        default=MemoryFactStatus.CURRENT,
        nullable=False,
        index=True,
    )
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(Integer, default=50, nullable=False, index=True)
    visibility_scope: Mapped[VisibilityScope] = mapped_column(
        Enum(VisibilityScope, name="visibility_scope"),
        default=VisibilityScope.MANAGER_ONLY,
        nullable=False,
        index=True,
    )


class MemoryEvidenceLink(Base):
    __tablename__ = "memory_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "memory_kind", "memory_id", "memory_source_id", name="uq_memory_evidence_link"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    memory_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemorySummary(Base):
    __tablename__ = "memory_summaries"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "entity_id",
            "period_start",
            "period_end",
            name="uq_memory_summaries_scope_period",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ManagementProcedure(TimestampMixin, Base):
    __tablename__ = "management_procedures"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    suggested_actions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[ManagementProcedureStatus] = mapped_column(
        Enum(ManagementProcedureStatus, name="management_procedure_status"),
        default=ManagementProcedureStatus.CANDIDATE,
        nullable=False,
        index=True,
    )
    supporting_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MemoryJob(TimestampMixin, Base):
    __tablename__ = "memory_jobs"
    __table_args__ = (UniqueConstraint("job_type", "source_id", name="uq_memory_jobs_type_source"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[MemoryJobStatus] = mapped_column(
        Enum(MemoryJobStatus, name="memory_job_status"),
        default=MemoryJobStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
