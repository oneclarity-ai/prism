"""Small relational conversation state and per-owner dependency progress."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class BlockerDependency(TimestampMixin, Base):
    __tablename__ = "blocker_dependencies"
    __table_args__ = (UniqueConstraint("blocker_id", "employee_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("blockers.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    employee = relationship("Employee")


class ConversationQuestion(TimestampMixin, Base):
    """More than one question may be outstanding in the same chat."""
    __tablename__ = "conversation_questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), unique=True)
    blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("blockers.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    awaiting_field: Mapped[str] = mapped_column(String(40))
    expected_answer_type: Mapped[Optional[str]] = mapped_column(String(40))
    asked_to_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    related_commitment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("commitments.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="awaiting_response", server_default="awaiting_response", index=True)
    answered_by_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ConversationState(TimestampMixin, Base):
    __tablename__ = "conversation_states"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    last_user_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    active_blocker_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("blockers.id", ondelete="SET NULL"))
    active_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
