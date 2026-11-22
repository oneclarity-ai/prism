import uuid

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.enums import TaskStatus


class Task(IdMixin, TimestampMixin, Base):
    """A unit of work for one agent. parent_id keeps Paperclip's goal -> task tree."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_agent_status", "agent_id", "status"),
        UniqueConstraint("org_id", "operation_key", name="uq_tasks_org_operation_key"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    goal: Mapped[str] = mapped_column(Text, default="")
    # e.g. {"urls": [...], "features": [...], "acceptance_criteria": [...], "allow_bug_filing": false}
    scope: Mapped[dict] = mapped_column(JSONB, default=dict)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"))
    target_app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("target_apps.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.todo)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    operation_key: Mapped[str | None] = mapped_column(String(200))
