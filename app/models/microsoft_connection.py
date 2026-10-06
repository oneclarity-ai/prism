from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.automation_run import AutomationRun
    from app.models.microsoft_subscription import MicrosoftTeamsSubscription


class MicrosoftConnection(TimestampMixin, Base):
    """The one approved delegated Microsoft Graph connection for this local app."""

    __tablename__ = "microsoft_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        UniqueConstraint("microsoft_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    microsoft_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_principal_name: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_scopes: Mapped[str] = mapped_column(Text, nullable=False)
    last_connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    automation_runs: Mapped[list["AutomationRun"]] = relationship(
        "AutomationRun", back_populates="connection"
    )
    subscriptions: Mapped[list["MicrosoftTeamsSubscription"]] = relationship(
        "MicrosoftTeamsSubscription", back_populates="connection"
    )
