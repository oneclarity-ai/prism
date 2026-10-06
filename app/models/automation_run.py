from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import AutomationStatus

if TYPE_CHECKING:
    from app.models.microsoft_connection import MicrosoftConnection
    from app.models.microsoft_subscription import MicrosoftTeamsSubscription


class AutomationRun(TimestampMixin, Base):
    """An auditable start/stop session for Teams management automation."""

    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("microsoft_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus, name="automation_status"),
        default=AutomationStatus.RUNNING,
        nullable=False,
        index=True,
    )
    initial_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    target_employee_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    connection: Mapped["MicrosoftConnection"] = relationship(
        "MicrosoftConnection", back_populates="automation_runs"
    )
    subscriptions: Mapped[list["MicrosoftTeamsSubscription"]] = relationship(
        "MicrosoftTeamsSubscription", back_populates="automation_run"
    )
