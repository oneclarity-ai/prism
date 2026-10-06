from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app
from app.models.agent_run import AgentRun
from app.models.blocker import Blocker
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.enums import (
    AgentAnalysisType,
    AgentRunStatus,
    BlockerSeverity,
    ConversationChannel,
    ConversationType,
    MessageDirection,
    SenderType,
)
from app.models.message import Message


def test_journey_shows_the_stored_blocker_message_chain() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    conversation_ids: list[uuid.UUID] = []
    message_ids: list[uuid.UUID] = []
    blocker_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    try:
        with SessionLocal() as db:
            jambu = Employee(name="Jambu Test", email="jambu-{}@example.invalid".format(suffix), role="Engineer")
            shubham = Employee(name="Shubham Test", email="shubham-{}@example.invalid".format(suffix), role="Engineer")
            db.add_all([jambu, shubham])
            db.flush()
            employee_ids = [jambu.id, shubham.id]
            blocker = Blocker(
                blocked_employee_id=jambu.id,
                dependency_owner_id=shubham.id,
                description="Updated schema is needed before the API work can continue",
                severity=BlockerSeverity.HIGH,
            )
            jambu_chat = Conversation(
                employee_id=jambu.id,
                channel=ConversationChannel.TEAMS,
                conversation_type=ConversationType.DIRECT,
                started_at=datetime.now(timezone.utc),
            )
            shubham_chat = Conversation(
                employee_id=shubham.id,
                channel=ConversationChannel.TEAMS,
                conversation_type=ConversationType.DIRECT,
                started_at=datetime.now(timezone.utc),
            )
            db.add_all([blocker, jambu_chat, shubham_chat])
            db.flush()
            blocker_id = blocker.id
            conversation_ids = [jambu_chat.id, shubham_chat.id]
            inbound = Message(conversation_id=jambu_chat.id, employee_id=jambu.id, direction=MessageDirection.INBOUND, sender_type=SenderType.EMPLOYEE, content="I am blocked because Shubham has not sent the updated schema.")
            acknowledgement = Message(conversation_id=jambu_chat.id, employee_id=jambu.id, direction=MessageDirection.OUTBOUND, sender_type=SenderType.YASH, content="Hi Jambu, I will check with Shubham and get back to you.")
            dependency_request = Message(conversation_id=shubham_chat.id, employee_id=shubham.id, direction=MessageDirection.OUTBOUND, sender_type=SenderType.YASH, content="Hi Shubham, Jambu is waiting on the updated schema. Any idea when this might be ready?")
            db.add_all([inbound, acknowledgement, dependency_request])
            db.flush()
            message_ids = [inbound.id, acknowledgement.id, dependency_request.id]
            run = AgentRun(
                inbound_message_id=inbound.id,
                source_employee_id=jambu.id,
                status=AgentRunStatus.COMPLETED,
                analysis_type=AgentAnalysisType.BLOCKER,
                blocker_id=blocker.id,
                dependency_owner_id=shubham.id,
                source_reply_message_id=acknowledgement.id,
                dependency_message_id=dependency_request.id,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = TestClient(app).get("/api/v1/management/journeys")

        assert response.status_code == 200
        journey = next(item for item in response.json() if item["blocker_id"] == str(blocker_id))
        assert journey["title"] == "Jambu's blocker"
        assert journey["dependency_owner_name"] == "Shubham"
        assert [event["title"] for event in journey["events"]] == [
            "Jambu raised the blocker",
            "Agent updated Jambu",
            "Agent asked Shubham for an ETA",
        ]
    finally:
        with SessionLocal() as db:
            if run_id is not None:
                db.execute(delete(AgentRun).where(AgentRun.id == run_id))
            if message_ids:
                db.execute(delete(Message).where(Message.id.in_(message_ids)))
            if conversation_ids:
                db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
