from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BlockerSeverity, BlockerStatus

if TYPE_CHECKING:
    from app.models.commitment import Commitment
    from app.models.employee import Employee
    from app.models.response_state import BlockerDependency
    from app.models.task import Task


class Blocker(TimestampMixin, Base):
    __tablename__ = "blockers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    blocked_employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dependency_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[BlockerStatus] = mapped_column(
        Enum(BlockerStatus, name="blocker_status"),
        default=BlockerStatus.OPEN,
        nullable=False,
        index=True,
    )
    severity: Mapped[BlockerSeverity] = mapped_column(
        Enum(BlockerSeverity, name="blocker_severity"),
        default=BlockerSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="blockers")
    blocked_employee: Mapped["Employee"] = relationship(
        "Employee", foreign_keys=[blocked_employee_id], back_populates="blockers"
    )
    dependency_owner: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[dependency_owner_id], back_populates="dependency_blockers"
    )
    commitments: Mapped[list["Commitment"]] = relationship("Commitment", back_populates="blocker")
    dependencies: Mapped[list["BlockerDependency"]] = relationship(
        "BlockerDependency", passive_deletes=True
    )

    @property
    def dependency_owner_ids(self) -> list[uuid.UUID]:
        owners = [item.employee_id for item in self.dependencies if item.is_active]
        return owners or ([self.dependency_owner_id] if self.dependency_owner_id else [])
