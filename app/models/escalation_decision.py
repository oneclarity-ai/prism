from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EscalationDecisionType

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.escalation import Escalation


class EscalationDecision(Base):
    """The one deliberate manager decision allowed for a protected escalation."""

    __tablename__ = "escalation_decisions"
    __table_args__ = (UniqueConstraint("escalation_id", name="uq_escalation_decisions_escalation"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[EscalationDecisionType] = mapped_column(
        Enum(EscalationDecisionType, name="escalation_decision_type"), nullable=False, index=True
    )
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    authorized_action: Mapped[Optional[str]] = mapped_column(String(100))

    escalation: Mapped["Escalation"] = relationship("Escalation", back_populates="decisions")
    decider: Mapped["Employee"] = relationship("Employee")
