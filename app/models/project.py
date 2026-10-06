from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import Priority, ProjectStatus

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.escalation import Escalation
    from app.models.task import Task


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        default=ProjectStatus.PLANNING,
        nullable=False,
        index=True,
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority"), default=Priority.MEDIUM, nullable=False, index=True
    )
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date, index=True)

    owner: Mapped[Optional["Employee"]] = relationship("Employee", back_populates="owned_projects")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project")
    escalations: Mapped[list["Escalation"]] = relationship("Escalation", back_populates="project")
