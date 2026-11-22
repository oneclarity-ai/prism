from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models.enums import (
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.schemas.common import ORMResponse, Schema


class MessageIntentCreate(Schema):
    employee_id: uuid.UUID
    content: str = Field(min_length=1)
    channel: ConversationChannel = ConversationChannel.INTERNAL
    conversation_id: Optional[uuid.UUID] = None


class ConversationRead(ORMResponse):
    id: uuid.UUID
    employee_id: Optional[uuid.UUID]
    channel: ConversationChannel
    external_conversation_id: Optional[str]
    conversation_type: ConversationType
    started_at: datetime
    last_message_at: Optional[datetime]
    created_at: datetime


class MessageRead(ORMResponse):
    id: uuid.UUID
    conversation_id: uuid.UUID
    employee_id: Optional[uuid.UUID]
    direction: MessageDirection
    sender_type: SenderType
    delivery_status: MessageDeliveryStatus
    external_message_id: Optional[str]
    external_created_at: Optional[datetime]
    content: str
    reply_to_external_id: Optional[str]
    quoted_content: Optional[str]
    created_at: datetime
    updated_at: datetime
