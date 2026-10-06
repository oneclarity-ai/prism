"""Durable V2 intelligence records built above operational source-of-truth tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DependencyEdge(TimestampMixin, Base):
    """Temporal adjacency-list edge; PostgreSQL is sufficient for V2 graph traversal."""

    __tablename__ = "dependency_edges"
    __table_args__ = (
        Index("ix_dependency_edges_source", "source_entity_type", "source_entity_id", "status"),
        Index("ix_dependency_edges_target", "target_entity_type", "target_entity_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), default="depends_on", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blockers.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    reopened_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dependency_edges.id", ondelete="SET NULL"), index=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)


class ManagementRisk(TimestampMixin, Base):
    """Explainable, source-backed risk signal. It is a hypothesis, not operational truth."""

    __tablename__ = "management_risks"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_management_risks_fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False)
    affected_entities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    signals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    deadline_at_risk: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)


class ManagementDecision(TimestampMixin, Base):
    """Validated proactive decision and concise rationale; never hidden chain-of-thought."""

    __tablename__ = "management_decisions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_management_decisions_idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="recommended", nullable=False, index=True)
    target_employee_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    related_issue_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    outcome: Mapped[Optional[dict]] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ManagerFeedback(TimestampMixin, Base):
    """Explicit, scoped correction or preference supplied by the manager."""

    __tablename__ = "manager_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instruction_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
