from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import CommitmentStatus

if TYPE_CHECKING:
    from app.models.blocker import Blocker
    from app.models.employee import Employee
    from app.models.task import Task


class Commitment(TimestampMixin, Base):
    __tablename__ = "commitments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blockers.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[CommitmentStatus] = mapped_column(
        Enum(CommitmentStatus, name="commitment_status"),
        default=CommitmentStatus.OPEN,
        nullable=False,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    missed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    missed_reason: Mapped[Optional[str]] = mapped_column(Text)
    revised_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commitments.id", ondelete="SET NULL"), index=True
    )
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="commitments")
    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="commitments")
    blocker: Mapped[Optional["Blocker"]] = relationship("Blocker", back_populates="commitments")
    revised_from: Mapped[Optional["Commitment"]] = relationship(
        "Commitment", remote_side="Commitment.id", back_populates="revisions"
    )
    revisions: Mapped[list["Commitment"]] = relationship(
        "Commitment", back_populates="revised_from"
    )
