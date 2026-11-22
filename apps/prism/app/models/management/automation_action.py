from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import AutomationActionStatus, AutomationActionType


class AutomationAction(TimestampMixin, Base):
    """Idempotent audit record for one deterministic scheduled action."""

    __tablename__ = "automation_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type: Mapped[AutomationActionType] = mapped_column(
        Enum(AutomationActionType, name="automation_action_type"), nullable=False, index=True
    )
    status: Mapped[AutomationActionStatus] = mapped_column(
        Enum(AutomationActionStatus, name="automation_action_status"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    commitment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commitments.id", ondelete="SET NULL"), index=True
    )
    blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blockers.id", ondelete="SET NULL"), index=True
    )
    escalation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalations.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    detail: Mapped[Optional[str]] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    employee = relationship("Employee")
    commitment = relationship("Commitment")
    blocker = relationship("Blocker")
    escalation = relationship("Escalation")
    message = relationship("Message")
