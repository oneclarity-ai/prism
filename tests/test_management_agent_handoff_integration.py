from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.agents.management_agent import ManagementAgent
from app.db.session import SessionLocal
from app.models.agent_run import AgentRun
from app.models.automation_action import AutomationAction
from app.models.blocker import Blocker
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.enums import (
    AgentRunStatus,
    BlockerStatus,
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.models.response_state import ConversationQuestion
from app.services.microsoft_service import MicrosoftService
from app.services.response_service import ResponseService
from app.schemas.response_decision import ResponseDecision, IssueDecision, OutgoingDecision


def test_named_owner_handoff_acknowledges_source_and_contacts_owner(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    conversation_ids: list[uuid.UUID] = []
    blocker_id: uuid.UUID | None = None
    sent: list[tuple[str, str]] = []

    with SessionLocal() as db:
        source = Employee(
            name="Ajay Test",
            email="ajay-handoff-{}@example.invalid".format(suffix),
            role="Engineer",
            teams_user_id="test-ajay-{}".format(suffix),
            is_managed=True,
        )
        owner_first_name = "Owner" + suffix[:8]
        owner = Employee(
            name=owner_first_name + " Test",
            email="vaibhav-handoff-{}@example.invalid".format(suffix),
            role="Engineer",
            teams_user_id="test-vaibhav-{}".format(suffix),
            is_managed=True,
        )
        db.add_all([source, owner])
        db.flush()
        employee_ids = [source.id, owner.id]
        source_conversation = Conversation(
            employee_id=source.id,
            channel=ConversationChannel.TEAMS,
            conversation_type=ConversationType.DIRECT,
            started_at=datetime.now(timezone.utc),
        )
        owner_conversation = Conversation(
            employee_id=owner.id,
            channel=ConversationChannel.TEAMS,
            conversation_type=ConversationType.DIRECT,
            started_at=datetime.now(timezone.utc),
        )
        db.add_all([source_conversation, owner_conversation])
        db.flush()
        conversation_ids = [source_conversation.id, owner_conversation.id]
        blocker = Blocker(
            blocked_employee_id=source.id,
            description="Status API changes are needed before connector work can continue",
        )
        db.add(blocker)
        db.flush()
        blocker_id = blocker.id
        owner_question = Message(
            conversation_id=source_conversation.id,
            employee_id=source.id,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.AGENT,
            delivery_status=MessageDeliveryStatus.DELIVERED,
            content="Who specifically owns the dependency?",
            external_message_id="owner-question-{}".format(suffix),
        )
        db.add(owner_question)
        db.flush()
        handoff = Message(
            conversation_id=source_conversation.id,
            employee_id=source.id,
            direction=MessageDirection.INBOUND,
            sender_type=SenderType.EMPLOYEE,
            delivery_status=MessageDeliveryStatus.DELIVERED,
            content="You can follow this with " + owner_first_name,
            reply_to_external_id=owner_question.external_message_id,
        )
        db.add(handoff)
        db.add(ConversationQuestion(
            conversation_id=source_conversation.id,
            message_id=owner_question.id,
            blocker_id=blocker.id,
            awaiting_field="owner",
            asked_to_employee_id=source.id,
        ))
        db.flush()
        db.add(
            AgentRun(
                inbound_message_id=owner_question.id,
                source_employee_id=source.id,
                status=AgentRunStatus.COMPLETED,
                blocker_id=blocker.id,
                source_reply_message_id=owner_question.id,
                processed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        def fake_send(db_session, recipient, content):
            conversation_id = source_conversation.id if recipient.id == source.id else owner_conversation.id
            message = Message(
                conversation_id=conversation_id,
                employee_id=recipient.id,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.AGENT,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                content=content,
            )
            db_session.add(message)
            db_session.flush()
            sent.append((recipient.name, content))
            return message

        def decision_for_handoff(context, message):
            return ResponseDecision(should_respond=True, response_type="dependency_followup", reason="Explicit owner answer",
                confidence=.99, needs_clarification=False, issues=[IssueDecision(key="api", blocker_id=blocker.id,
                    operation="set_owners", description=blocker.description, dependency_owner_ids=[owner.id], evidence=message.content)],
                messages=[OutgoingDecision(recipient_id=source.id, issue_key="api", kind="acknowledgement",
                    text="Thanks, I've noted that {} owns this.".format(owner_first_name)),
                    OutgoingDecision(recipient_id=owner.id, issue_key="api", kind="dependency_followup",
                        text="The status API changes are needed. Any idea when this might be ready?", awaiting_field="eta")])

        active_run = SimpleNamespace(target_employee_ids=[str(source.id), str(owner.id)])
        monkeypatch.setattr(MicrosoftService, "send_management_message", fake_send)
        monkeypatch.setattr(MicrosoftService, "active_run", staticmethod(lambda _db: active_run))
        monkeypatch.setattr(ResponseService, "decide", staticmethod(decision_for_handoff))

        result = ManagementAgent.process_message(db, str(handoff.id))
        db.refresh(blocker)

        assert result is not None
        assert blocker.dependency_owner_id == owner.id
        assert [name for name, _ in sent] == ["Ajay Test", owner_first_name + " Test"]
        assert "noted that {} owns this".format(owner_first_name) in sent[0][1]
        assert "Any idea when this might be ready?" in sent[1][1]

    with SessionLocal() as db:
        if blocker_id is not None:
            db.execute(delete(AutomationAction).where(AutomationAction.blocker_id == blocker_id))
        if employee_ids:
            db.execute(delete(AgentRun).where(AgentRun.source_employee_id.in_(employee_ids)))
        if conversation_ids:
            db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
        if blocker_id is not None:
            db.execute(delete(Blocker).where(Blocker.id == blocker_id))
        if conversation_ids:
            db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
        if employee_ids:
            db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
        db.commit()
