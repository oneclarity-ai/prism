from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.message import Message


def test_teams_message_intent_is_recorded_without_delivery() -> None:
    suffix = uuid.uuid4().hex[:12]
    client = TestClient(app)
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message_ids: list[str] = []

    try:
        employee = client.post(
            "/api/v1/employees",
            json={"name": "Intent Recipient", "email": "intent-{}@example.invalid".format(suffix), "role": "Engineer"},
        )
        assert employee.status_code == 201
        employee_id = employee.json()["id"]

        first_intent = client.post(
            "/api/v1/message-intents",
            json={
                "employee_id": employee_id,
                "channel": "teams",
                "content": "Please provide an ETA for the updated schema.",
            },
        )
        assert first_intent.status_code == 201
        first_message = first_intent.json()
        message_ids.append(first_message["id"])
        conversation_id = first_message["conversation_id"]
        assert first_message["delivery_status"] == "recorded"
        assert first_message["external_message_id"] is None
        assert first_message["sender_type"] == "agent"

        second_intent = client.post(
            "/api/v1/message-intents",
            json={
                "employee_id": employee_id,
                "channel": "teams",
                "content": "The commitment will be tracked once you reply.",
            },
        )
        assert second_intent.status_code == 201
        message_ids.append(second_intent.json()["id"])
        assert second_intent.json()["conversation_id"] == conversation_id

        conversations = client.get("/api/v1/conversations", params={"employee_id": employee_id})
        assert conversations.status_code == 200
        assert conversations.json()["total"] == 1
        assert conversations.json()["items"][0]["channel"] == "teams"

        messages = client.get("/api/v1/messages", params={"conversation_id": conversation_id})
        assert messages.status_code == 200
        assert messages.json()["total"] == 2
    finally:
        with SessionLocal() as db:
            if message_ids:
                db.execute(delete(Message).where(Message.id.in_(message_ids)))
            if conversation_id is not None:
                db.execute(delete(Conversation).where(Conversation.id == conversation_id))
            if employee_id is not None:
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
