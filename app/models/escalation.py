from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BlockerSeverity, EscalationStatus, EscalationType

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.escalation_decision import EscalationDecision
    from app.models.project import Project
    from app.models.task import Task


class Escalation(TimestampMixin, Base):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    escalation_type: Mapped[EscalationType] = mapped_column(
        Enum(EscalationType, name="escalation_type"), nullable=False, index=True
    )
    severity: Mapped[BlockerSeverity] = mapped_column(
        Enum(BlockerSeverity, name="blocker_severity"),
        default=BlockerSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text)
    requested_target_date: Mapped[Optional[date]] = mapped_column(Date)
    requested_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"),
        default=EscalationStatus.OPEN,
        nullable=False,
        index=True,
    )
    requires_manager_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Optional["Employee"]] = relationship("Employee")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="escalations")
    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="escalations")
    decisions: Mapped[list["EscalationDecision"]] = relationship(
        "EscalationDecision", back_populates="escalation", order_by="EscalationDecision.decided_at"
    )
