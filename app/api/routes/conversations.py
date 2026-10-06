from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ConversationChannel, MessageDeliveryStatus, MessageDirection
from app.schemas.common import Page
from app.schemas.conversation import ConversationRead, MessageIntentCreate, MessageRead
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/api/v1", tags=["conversations and messages"])


@router.post("/message-intents", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message_intent(payload: MessageIntentCreate, db: Session = Depends(get_db)) -> MessageRead:
    return ConversationService.create_message_intent(db, payload)


@router.get("/conversations", response_model=Page[ConversationRead])
def list_conversations(
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    channel: Optional[ConversationChannel] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ConversationRead]:
    conversations, total = ConversationService.list_conversations(
        db, employee_id=employee_id, channel=channel, limit=limit, offset=offset
    )
    return Page[ConversationRead](items=conversations, total=total, limit=limit, offset=offset)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationRead:
    return ConversationService.get_conversation(db, conversation_id)


@router.get("/messages", response_model=Page[MessageRead])
def list_messages(
    db: Session = Depends(get_db),
    conversation_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    direction: Optional[MessageDirection] = None,
    delivery_status: Optional[MessageDeliveryStatus] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MessageRead]:
    messages, total = ConversationService.list_messages(
        db,
        conversation_id=conversation_id,
        employee_id=employee_id,
        direction=direction,
        delivery_status=delivery_status,
        limit=limit,
        offset=offset,
    )
    return Page[MessageRead](items=messages, total=total, limit=limit, offset=offset)
