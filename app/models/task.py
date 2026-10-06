from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import Priority, TaskStatus

if TYPE_CHECKING:
    from app.models.blocker import Blocker
    from app.models.commitment import Commitment
    from app.models.employee import Employee
    from app.models.escalation import Escalation
    from app.models.project import Project


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.TODO, nullable=False, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority"), default=Priority.MEDIUM, nullable=False, index=True
    )
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="tasks")
    owner: Mapped["Employee"] = relationship("Employee", back_populates="assigned_tasks")
    commitments: Mapped[list["Commitment"]] = relationship("Commitment", back_populates="task")
    blockers: Mapped[list["Blocker"]] = relationship("Blocker", back_populates="task")
    escalations: Mapped[list["Escalation"]] = relationship("Escalation", back_populates="task")
