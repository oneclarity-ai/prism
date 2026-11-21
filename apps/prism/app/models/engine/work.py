from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PrismComputer(TimestampMixin, Base):
    """A Prism's computer in the hidden engine: its agent and its browser container."""

    __tablename__ = "prism_computers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prisms.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    computer_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    swarm_agent_id: Mapped[Optional[str]] = mapped_column(String(64))
    agent_hash: Mapped[Optional[str]] = mapped_column(String(64))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PrismLogin(TimestampMixin, Base):
    """A login the manager gave a Prism for one site. The password lives only in the engine, encrypted."""

    __tablename__ = "prism_logins"
    __table_args__ = (
        UniqueConstraint("prism_id", "origin"),
        Index("ix_prism_logins_prism", "prism_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(300), nullable=False)
    username_masked: Mapped[str] = mapped_column(String(120), nullable=False)
    swarm_secret_id: Mapped[Optional[str]] = mapped_column(String(64))
    remember: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
