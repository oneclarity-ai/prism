from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

BRAIN_STATUSES = ("approved", "proposed", "rejected")
BRAIN_SOURCES = ("user", "chat", "prism")


class BrainEntry(TimestampMixin, Base):
    """One thing every Prism should know about the organisation, or what a Prism is working on."""

    __tablename__ = "brain_entries"
    __table_args__ = (Index("ix_brain_entries_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # approved: Prisms use it. proposed: learned from a chat, waits for the user. rejected: kept so it is not re-proposed.
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="approved", server_default="approved"
    )
    # user: written by the user. chat: learned from a conversation. prism: a Prism's own work note.
    source: Mapped[str] = mapped_column(
        String(8), nullable=False, default="user", server_default="user"
    )
    prism_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), index=True
    )
