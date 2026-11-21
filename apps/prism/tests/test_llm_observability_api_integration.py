from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.main import app
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.enums import (
    AgentRunStatus,
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.models.llm_usage import LLMUsage
from app.models.message import Message


def test_llm_usage_and_decision_debug_apis_report_actual_rows():
    employee_id = conversation_id = message_id = run_id = usage_id = None
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        employee = Employee(
            name="Usage Tester (dummy)",
            email="usage-{}@example.invalid".format(suffix),
            role="Tester",
        )
        db.add(employee)
        db.flush()
        employee_id = employee.id
        conversation = Conversation(
            employee_id=employee.id,
            channel=ConversationChannel.TEAMS,
            conversation_type=ConversationType.DIRECT,
            started_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
        message = Message(
            conversation_id=conversation.id,
            employee_id=employee.id,
            direction=MessageDirection.INBOUND,
            sender_type=SenderType.EMPLOYEE,
            delivery_status=MessageDeliveryStatus.DELIVERED,
            content="Testing usage visibility",
            created_at=datetime.now(timezone.utc),
        )
        db.add(message)
        db.flush()
        message_id = message.id
        run = AgentRun(
            inbound_message_id=message.id,
            source_employee_id=employee.id,
            status=AgentRunStatus.COMPLETED,
            model_deployment="dummy-small",
            state_applied=True,
            decision_json={"response_type": "acknowledgement"},
            context_json={"context_source_ids": [str(message.id)]},
        )
        db.add(run)
        db.flush()
        run_id = run.id
        usage = LLMUsage(
            model="dummy-model",
            deployment="dummy-small",
            feature="response_decisions",
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=25,
            total_tokens=125,
            estimated_input_cost_usd=Decimal("0.001"),
            estimated_output_cost_usd=Decimal("0.002"),
            estimated_total_cost_usd=Decimal("0.003"),
            latency_ms=42,
            status="completed",
            message_id=message.id,
            conversation_id=conversation.id,
            user_id=employee.id,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(usage)
        db.commit()
        usage_id = usage.id

    try:
        client = TestClient(app)
        today = client.get("/api/v1/usage/llm/today")
        assert today.status_code == 200
        assert today.json()["calls"] >= 1
        assert Decimal(today.json()["estimated_cost_usd"]) >= Decimal("0.003")
        assert any(
            row["group"] == "dummy-model" for row in client.get("/api/v1/usage/llm/by-model").json()
        )
        assert any(
            row["group"] == "response_decisions"
            for row in client.get("/api/v1/usage/llm/by-feature").json()
        )

        runs = client.get("/api/v1/microsoft/agent/runs", params={"message_id": str(message_id)})
        assert runs.status_code == 200 and len(runs.json()) == 1
        item = runs.json()[0]
        assert item["decision"]["response_type"] == "acknowledgement"
        assert item["context"] is None
        assert item["context_source_ids"] == [str(message_id)]
        assert item["llm_calls"] == 1 and item["input_tokens"] == 100
        assert Decimal(item["estimated_cost_usd"]) == Decimal("0.003")
    finally:
        with SessionLocal() as db:
            if usage_id:
                db.execute(delete(LLMUsage).where(LLMUsage.id == usage_id))
            if run_id:
                db.execute(delete(AgentRun).where(AgentRun.id == run_id))
            if message_id:
                db.execute(delete(Message).where(Message.id == message_id))
            if conversation_id:
                db.execute(delete(Conversation).where(Conversation.id == conversation_id))
            if employee_id:
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
