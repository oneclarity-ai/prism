from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MicrosoftSubscriptionStatus

if TYPE_CHECKING:
    from app.models.automation_run import AutomationRun
    from app.models.conversation import Conversation
    from app.models.microsoft_connection import MicrosoftConnection


class MicrosoftTeamsSubscription(TimestampMixin, Base):
    """A Microsoft Graph change-notification subscription for one direct chat."""

    __tablename__ = "microsoft_teams_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("microsoft_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    automation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_runs.id", ondelete="SET NULL"),
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_subscription_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_client_state: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[MicrosoftSubscriptionStatus] = mapped_column(
        Enum(MicrosoftSubscriptionStatus, name="microsoft_subscription_status"),
        default=MicrosoftSubscriptionStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    connection: Mapped["MicrosoftConnection"] = relationship(
        "MicrosoftConnection", back_populates="subscriptions"
    )
    automation_run: Mapped[Optional["AutomationRun"]] = relationship(
        "AutomationRun", back_populates="subscriptions"
    )
    conversation: Mapped["Conversation"] = relationship("Conversation")
