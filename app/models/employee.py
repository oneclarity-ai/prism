from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.blocker import Blocker
    from app.models.commitment import Commitment
    from app.models.conversation import Conversation
    from app.models.daily_update import DailyUpdate
    from app.models.employee_alias import EmployeeAlias
    from app.models.project import Project
    from app.models.task import Task


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    teams_user_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_managed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )

    manager: Mapped[Optional["Employee"]] = relationship(
        "Employee", remote_side="Employee.id", back_populates="direct_reports"
    )
    direct_reports: Mapped[list["Employee"]] = relationship("Employee", back_populates="manager")
    owned_projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner")
    assigned_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="owner")
    commitments: Mapped[list["Commitment"]] = relationship("Commitment", back_populates="employee")
    blockers: Mapped[list["Blocker"]] = relationship(
        "Blocker", foreign_keys="Blocker.blocked_employee_id", back_populates="blocked_employee"
    )
    dependency_blockers: Mapped[list["Blocker"]] = relationship(
        "Blocker", foreign_keys="Blocker.dependency_owner_id", back_populates="dependency_owner"
    )
    daily_updates: Mapped[list["DailyUpdate"]] = relationship(
        "DailyUpdate", back_populates="employee"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="employee"
    )
    alias_records: Mapped[list["EmployeeAlias"]] = relationship(
        "EmployeeAlias", back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def aliases(self) -> list[str]:
        return [record.alias for record in self.alias_records]
