from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

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
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import (
    BlockerStatus,
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.services.microsoft_service import MicrosoftService
from app.services.response_service import ResponseService
from app.models.enums import AgentRunStatus
from app.schemas.response_decision import ResponseDecision, IssueDecision, OutgoingDecision


def test_same_blocker_can_send_only_one_acknowledgement_and_owner_request(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    conversation_ids: list[uuid.UUID] = []
    blocker_id: uuid.UUID | None = None
    run_ids: list[uuid.UUID] = []
    sent_message_ids: list[uuid.UUID] = []
    sent: list[tuple[uuid.UUID, str]] = []
    try:
        with SessionLocal() as db:
            source = Employee(name="Shivam Safety", email="shivam-{}@example.invalid".format(suffix), role="Engineer", teams_user_id="shivam-{}".format(suffix))
            owner = Employee(name="Ajay Safety", email="ajay-{}@example.invalid".format(suffix), role="Engineer", teams_user_id="ajay-{}".format(suffix))
            db.add_all([source, owner]); db.flush()
            employee_ids = [source.id, owner.id]
            source_chat = Conversation(employee_id=source.id, channel=ConversationChannel.TEAMS, conversation_type=ConversationType.DIRECT, started_at=datetime.now(timezone.utc))
            owner_chat = Conversation(employee_id=owner.id, channel=ConversationChannel.TEAMS, conversation_type=ConversationType.DIRECT, started_at=datetime.now(timezone.utc))
            db.add_all([source_chat, owner_chat]); db.flush()
            conversation_ids = [source_chat.id, owner_chat.id]
            blocker = Blocker(blocked_employee_id=source.id, dependency_owner_id=owner.id, description="Status API changes are needed", status=BlockerStatus.OPEN)
            db.add(blocker); db.flush(); blocker_id = blocker.id
            first_inbound = Message(conversation_id=source_chat.id, employee_id=source.id, direction=MessageDirection.INBOUND, sender_type=SenderType.EMPLOYEE, delivery_status=MessageDeliveryStatus.DELIVERED, content="Ajay owns it")
            second_inbound = Message(conversation_id=source_chat.id, employee_id=source.id, direction=MessageDirection.INBOUND, sender_type=SenderType.EMPLOYEE, delivery_status=MessageDeliveryStatus.DELIVERED, content="Ajay owns it")
            db.add_all([first_inbound, second_inbound]); db.flush()
            first_run = AgentRun(inbound_message_id=first_inbound.id, source_employee_id=source.id)
            second_run = AgentRun(inbound_message_id=second_inbound.id, source_employee_id=source.id)
            db.add_all([first_run, second_run]); db.commit()
            run_ids = [first_run.id, second_run.id]

            def fake_send(db_session, recipient, content):
                outbound = Message(
                    conversation_id=source_chat.id if recipient.id == source.id else owner_chat.id,
                    employee_id=recipient.id,
                    direction=MessageDirection.OUTBOUND,
                    sender_type=SenderType.AGENT,
                    delivery_status=MessageDeliveryStatus.DELIVERED,
                    content=content,
                )
                db_session.add(outbound); db_session.flush()
                sent.append((recipient.id, content)); sent_message_ids.append(outbound.id)
                return outbound

            monkeypatch.setattr(MicrosoftService, "send_management_message", fake_send)
            ManagementAgent._assign_dependency_owner_and_notify(db, first_run, source, owner, blocker.description, blocker=blocker)
            ManagementAgent._assign_dependency_owner_and_notify(db, second_run, source, owner, blocker.description, blocker=blocker)

            assert len(sent) == 2
            assert [recipient for recipient, _ in sent] == [source.id, owner.id]
            assert all("Safety" not in content for _, content in sent)
    finally:
        with SessionLocal() as db:
            if blocker_id is not None:
                db.execute(delete(AutomationAction).where(AutomationAction.blocker_id == blocker_id))
            if run_ids:
                db.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
            if sent_message_ids:
                db.execute(delete(Message).where(Message.id.in_(sent_message_ids)))
            if conversation_ids:
                db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if conversation_ids:
                db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()


def test_model_cannot_assign_an_owner_not_named_in_the_reply(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    conversation_ids: list[uuid.UUID] = []
    inbound_id: uuid.UUID | None = None
    blocker_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    sent_message_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            source = Employee(name="Shiva Safety", email="shiva-{}@example.invalid".format(suffix), role="Engineer", teams_user_id="shiva-{}".format(suffix), is_managed=True)
            unrelated = Employee(name="Shubham Safety", email="shubham-{}@example.invalid".format(suffix), role="Engineer", teams_user_id="shubham-{}".format(suffix))
            db.add_all([source, unrelated]); db.flush(); employee_ids = [source.id, unrelated.id]
            conversation = Conversation(employee_id=source.id, channel=ConversationChannel.TEAMS, conversation_type=ConversationType.DIRECT, started_at=datetime.now(timezone.utc))
            db.add(conversation); db.flush(); conversation_ids = [conversation.id]
            inbound = Message(conversation_id=conversation.id, employee_id=source.id, direction=MessageDirection.INBOUND, sender_type=SenderType.EMPLOYEE, delivery_status=MessageDeliveryStatus.DELIVERED, content="I am blocked waiting for the AI team to confirm the API.")
            db.add(inbound); db.commit(); inbound_id = inbound.id

            def fake_analysis(context, message):
                return ResponseDecision(should_respond=True, response_type="clarification", confidence=.95,
                    reason="The team is named but no individual owner is given", needs_clarification=True,
                    today_summary="Waiting for API confirmation", expected_outcome="API confirmation received",
                    issues=[IssueDecision(key="api", operation="report_blocker", description="API confirmation from the AI team is needed", evidence=message.content)],
                    messages=[OutgoingDecision(recipient_id=source.id, kind="clarification", issue_key="api",
                        text="Who specifically owns the API confirmation?", awaiting_field="owner")])

            def fake_send(db_session, recipient, content):
                outbound = Message(conversation_id=conversation.id, employee_id=recipient.id, direction=MessageDirection.OUTBOUND, sender_type=SenderType.AGENT, delivery_status=MessageDeliveryStatus.DELIVERED, content=content)
                db_session.add(outbound); db_session.flush(); sent_message_ids.append(outbound.id)
                return outbound

            monkeypatch.setattr(ResponseService, "decide", staticmethod(fake_analysis))
            monkeypatch.setattr(MicrosoftService, "send_management_message", fake_send)
            result = ManagementAgent.process_message(db, str(inbound.id))
            assert result is not None
            run_id = result.id
            blocker_id = result.blocker_id
            assert blocker_id is not None
            blocker = db.get(Blocker, blocker_id)
            assert blocker is not None and blocker.dependency_owner_id is None
            assert result.status == AgentRunStatus.COMPLETED
            assert len(sent_message_ids) == 1
            # A standalone blocker report with no named individual owner is handled
            # by the deterministic new_blocker_update fast path, so fake_analysis
            # above is never called; it documents what an LLM path must also refuse.
            assert "Who should I follow up with about this blocker" in db.get(Message, sent_message_ids[0]).content
            update = db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == source.id))
            assert update is not None
            assert update.today_summary == inbound.content
    finally:
        with SessionLocal() as db:
            if blocker_id is not None:
                db.execute(delete(AutomationAction).where(AutomationAction.blocker_id == blocker_id))
            if run_id is not None:
                db.execute(delete(AgentRun).where(AgentRun.id == run_id))
            if inbound_id is not None:
                db.execute(delete(Message).where(Message.id == inbound_id))
            if sent_message_ids:
                db.execute(delete(Message).where(Message.id.in_(sent_message_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if employee_ids:
                db.execute(delete(DailyUpdate).where(DailyUpdate.employee_id.in_(employee_ids)))
            if conversation_ids:
                db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
