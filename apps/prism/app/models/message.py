from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MessageDeliveryStatus, MessageDirection, SenderType

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.employee import Employee


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction"), nullable=False, index=True
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, name="sender_type"), nullable=False, index=True
    )
    delivery_status: Mapped[MessageDeliveryStatus] = mapped_column(
        Enum(MessageDeliveryStatus, name="message_delivery_status"),
        default=MessageDeliveryStatus.RECORDED,
        server_default="RECORDED",
        nullable=False,
        index=True,
    )
    external_message_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    external_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    quoted_content: Mapped[Optional[str]] = mapped_column(Text)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    employee: Mapped[Optional["Employee"]] = relationship("Employee")
