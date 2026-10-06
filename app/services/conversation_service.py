from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.enums import (
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.schemas.conversation import MessageIntentCreate
from app.services.common import get_employee
from app.services.errors import NotFoundError, RuleViolationError


class ConversationService:
    @staticmethod
    def create_message_intent(db: Session, data: MessageIntentCreate) -> Message:
        get_employee(db, data.employee_id)
        conversation = ConversationService._get_or_create_conversation(db, data)
        now = datetime.now(timezone.utc)
        message = Message(
            conversation_id=conversation.id,
            employee_id=data.employee_id,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.AGENT,
            delivery_status=MessageDeliveryStatus.RECORDED,
            content=data.content,
        )
        db.add(message)
        conversation.last_message_at = now
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def get_conversation(db: Session, conversation_id: uuid.UUID) -> Conversation:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation was not found")
        return conversation

    @staticmethod
    def list_conversations(
        db: Session,
        *,
        employee_id: uuid.UUID | None,
        channel: ConversationChannel | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        statement = select(Conversation).order_by(Conversation.last_message_at.desc().nullslast())
        count_statement = select(func.count()).select_from(Conversation)
        if employee_id is not None:
            statement = statement.where(Conversation.employee_id == employee_id)
            count_statement = count_statement.where(Conversation.employee_id == employee_id)
        if channel is not None:
            statement = statement.where(Conversation.channel == channel)
            count_statement = count_statement.where(Conversation.channel == channel)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def list_messages(
        db: Session,
        *,
        conversation_id: uuid.UUID | None,
        employee_id: uuid.UUID | None,
        direction: MessageDirection | None,
        delivery_status: MessageDeliveryStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Message], int]:
        statement = select(Message).order_by(Message.created_at.desc(), Message.id)
        count_statement = select(func.count()).select_from(Message)
        filters = [
            (Message.conversation_id, conversation_id),
            (Message.employee_id, employee_id),
            (Message.direction, direction),
            (Message.delivery_status, delivery_status),
        ]
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)
                count_statement = count_statement.where(column == value)
        return list(db.scalars(statement.limit(limit).offset(offset))), db.scalar(count_statement) or 0

    @staticmethod
    def _get_or_create_conversation(db: Session, data: MessageIntentCreate) -> Conversation:
        if data.conversation_id is not None:
            conversation = ConversationService.get_conversation(db, data.conversation_id)
            if conversation.employee_id != data.employee_id:
                raise RuleViolationError("Conversation does not belong to the intended employee")
            if conversation.channel != data.channel:
                raise RuleViolationError("Conversation channel does not match the message intent channel")
            return conversation

        conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.employee_id == data.employee_id,
                Conversation.channel == data.channel,
                Conversation.conversation_type == ConversationType.DIRECT,
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
            .limit(1)
        )
        if conversation is not None:
            return conversation

        now = datetime.now(timezone.utc)
        conversation = Conversation(
            employee_id=data.employee_id,
            channel=data.channel,
            conversation_type=ConversationType.DIRECT,
            started_at=now,
            last_message_at=now,
        )
        db.add(conversation)
        db.flush()
        return conversation
