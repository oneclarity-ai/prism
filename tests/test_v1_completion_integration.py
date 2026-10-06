from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_run import AgentRun
from app.models.automation_action import AutomationAction
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.conversation import Conversation
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import (
    ActivityEventType,
    AgentAnalysisType,
    AgentRunStatus,
    AutomationActionStatus,
    AutomationActionType,
    BlockerSeverity,
    BlockerStatus,
    CommitmentStatus,
    ConversationChannel,
    ConversationType,
    EscalationStatus,
    EscalationType,
    MessageDeliveryStatus,
    MessageDirection,
    SenderType,
)
from app.models.escalation import Escalation
from app.models.memory import ActivityEvent
from app.models.message import Message
from app.models.project import Project
from app.models.task import Task
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.schemas.daily_update import DailyUpdateCreate, DailyUpdateUpdate
from app.schemas.employee import EmployeeUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.automation_service import DailyAutomationService
from app.services.blocker_service import BlockerService
from app.services.daily_update_service import DailyUpdateService
from app.services.employee_service import EmployeeService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


def test_management_relevant_mutations_keep_before_after_events() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    entity_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            manager = Employee(
                name="Manager " + suffix,
                email="manager-events-{}@example.invalid".format(suffix),
                role="Manager",
            )
            first_owner = Employee(
                name="First " + suffix,
                email="first-events-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            second_owner = Employee(
                name="Second " + suffix,
                email="second-events-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            db.add_all([manager, first_owner, second_owner])
            db.commit()
            employee_ids = [manager.id, first_owner.id, second_owner.id]

            EmployeeService.update(db, second_owner.id, EmployeeUpdate(manager_id=manager.id))
            project = ProjectService.create(
                db, ProjectCreate(name="Events " + suffix, owner_id=first_owner.id)
            )
            ProjectService.update(db, project.id, ProjectUpdate(owner_id=second_owner.id))
            task = TaskService.create(
                db,
                TaskCreate(
                    owner_id=first_owner.id,
                    title="Events task " + suffix,
                    expected_outcome="A completed event trail",
                ),
            )
            TaskService.update(db, task.id, TaskUpdate(owner_id=second_owner.id))
            update = DailyUpdateService.create(
                db,
                DailyUpdateCreate(
                    employee_id=second_owner.id,
                    update_date=date.today(),
                    today_summary="Validate activity events",
                    expected_outcome="Every change has before and after values",
                ),
            )
            DailyUpdateService.update(
                db,
                update.id,
                DailyUpdateUpdate(expected_outcome="The event trail is queryable"),
            )
            blocker = BlockerService.create(
                db,
                BlockerCreate(
                    blocked_employee_id=second_owner.id,
                    description="Waiting for a management decision",
                    severity=BlockerSeverity.HIGH,
                ),
            )
            BlockerService.update(db, blocker.id, BlockerUpdate(dependency_owner_id=manager.id))
            BlockerService.update(db, blocker.id, BlockerUpdate(status=BlockerStatus.RESOLVED))
            entity_ids = [project.id, task.id, update.id, blocker.id, second_owner.id]

            events = list(
                db.scalars(select(ActivityEvent).where(ActivityEvent.entity_id.in_(entity_ids)))
            )
            types = {event.event_type for event in events}
            assert {
                ActivityEventType.EMPLOYEE_MANAGER_CHANGED,
                ActivityEventType.PROJECT_OWNER_CHANGED,
                ActivityEventType.TASK_OWNER_CHANGED,
                ActivityEventType.DAILY_UPDATE_CREATED,
                ActivityEventType.DAILY_UPDATE_CHANGED,
                ActivityEventType.BLOCKER_CREATED,
                ActivityEventType.BLOCKER_DEPENDENCY_OWNER_CHANGED,
                ActivityEventType.BLOCKER_STATUS_CHANGED,
                ActivityEventType.BLOCKER_RESOLVED,
            }.issubset(types)
            owner_event = next(
                event
                for event in events
                if event.event_type == ActivityEventType.BLOCKER_DEPENDENCY_OWNER_CHANGED
            )
            assert owner_event.metadata_json["previous"]["dependency_owner_id"] is None
            assert owner_event.metadata_json["new"]["dependency_owner_id"] == str(manager.id)
            update_event = next(
                event
                for event in events
                if event.event_type == ActivityEventType.DAILY_UPDATE_CHANGED
            )
            assert (
                update_event.metadata_json["previous"]["expected_outcome"]
                == "Every change has before and after values"
            )
            assert (
                update_event.metadata_json["new"]["expected_outcome"]
                == "The event trail is queryable"
            )
    finally:
        with SessionLocal() as db:
            if entity_ids:
                db.execute(delete(ActivityEvent).where(ActivityEvent.entity_id.in_(entity_ids)))
            if entity_ids:
                db.execute(delete(DailyUpdate).where(DailyUpdate.id.in_(entity_ids)))
                db.execute(delete(Blocker).where(Blocker.id.in_(entity_ids)))
                db.execute(delete(Task).where(Task.id.in_(entity_ids)))
                db.execute(delete(Project).where(Project.id.in_(entity_ids)))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()


def test_digest_uses_only_managed_team_and_structured_operational_state(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    try:
        local_now = datetime(2026, 9, 9, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        with SessionLocal() as db:
            avery = Employee(
                name="Avery " + suffix,
                email="avery-digest-{}@example.invalid".format(suffix),
                role="Engineer",
                teams_user_id="avery-digest-" + suffix,
                is_managed=True,
            )
            bailey = Employee(
                name="Bailey " + suffix,
                email="bailey-digest-{}@example.invalid".format(suffix),
                role="Engineer",
                teams_user_id="bailey-digest-" + suffix,
                is_managed=True,
            )
            outside = Employee(
                name="Outside " + suffix,
                email="outside-digest-{}@example.invalid".format(suffix),
                role="Engineer",
                teams_user_id="outside-digest-" + suffix,
                is_managed=False,
            )
            db.add_all([avery, bailey, outside])
            db.flush()
            employee_ids = [avery.id, bailey.id, outside.id]
            db.add_all(
                [
                    DailyUpdate(
                        employee_id=avery.id,
                        update_date=local_now.date(),
                        today_summary="Auth API",
                        expected_outcome="Staging endpoint ready",
                        blocker_summary="Waiting for schema",
                    ),
                    DailyUpdate(
                        employee_id=outside.id,
                        update_date=local_now.date(),
                        today_summary="Do not include this",
                        expected_outcome="Do not include this",
                    ),
                    Blocker(
                        blocked_employee_id=avery.id,
                        dependency_owner_id=bailey.id,
                        description="Waiting for schema",
                        severity=BlockerSeverity.HIGH,
                    ),
                    Commitment(
                        employee_id=avery.id,
                        description="Send the schema",
                        deadline=(local_now + timedelta(hours=1)).astimezone(timezone.utc),
                        status=CommitmentStatus.OPEN,
                    ),
                    Commitment(
                        employee_id=bailey.id,
                        description="Review the API",
                        deadline=(local_now + timedelta(days=1)).astimezone(timezone.utc),
                        status=CommitmentStatus.OPEN,
                    ),
                    Commitment(
                        employee_id=bailey.id,
                        description="Yesterday's promise",
                        deadline=(local_now - timedelta(days=1)).astimezone(timezone.utc),
                        status=CommitmentStatus.MISSED,
                        missed_at=(local_now - timedelta(hours=2)).astimezone(timezone.utc),
                    ),
                    Commitment(
                        employee_id=outside.id,
                        description="Outside team promise",
                        deadline=(local_now - timedelta(days=1)).astimezone(timezone.utc),
                        status=CommitmentStatus.MISSED,
                        missed_at=(local_now - timedelta(hours=2)).astimezone(timezone.utc),
                    ),
                    Escalation(
                        employee_id=avery.id,
                        escalation_type=EscalationType.PROJECT_DEADLINE_CHANGE,
                        severity=BlockerSeverity.HIGH,
                        reason="Approval is needed for target date",
                        status=EscalationStatus.PENDING_APPROVAL,
                        requires_manager_approval=True,
                    ),
                ]
            )
            db.commit()
            monkeypatch.setattr(
                DailyAutomationService,
                "_managed_team_employees",
                staticmethod(lambda _db: [avery, bailey]),
            )
            content = DailyAutomationService._daily_digest_content(db, local_now)
            managed_count = 2
            assert "Responded: 1/{}".format(managed_count) in content
            assert "Avery: Auth API" in content
            assert "Staging endpoint ready" in content
            assert "Waiting for schema (dependency: Bailey; severity: high)" in content
            assert "Commitments due today:" in content and "Send the schema" in content
            assert "Commitments due soon:" in content and "Review the API" in content
            assert "Missed commitments:" in content and "Yesterday's promise" in content
            assert "Needs approval:" in content and "Approval is needed for target date" in content
            assert "Outside team promise" not in content
            assert "Do not include this" not in content
    finally:
        with SessionLocal() as db:
            if employee_ids:
                db.execute(delete(Escalation).where(Escalation.employee_id.in_(employee_ids)))
                db.execute(delete(Commitment).where(Commitment.employee_id.in_(employee_ids)))
                db.execute(delete(Blocker).where(Blocker.blocked_employee_id.in_(employee_ids)))
                db.execute(delete(DailyUpdate).where(DailyUpdate.employee_id.in_(employee_ids)))
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()


def test_digest_explains_how_the_agent_handled_today_replies() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    conversation_ids: list[uuid.UUID] = []
    blocker_id: uuid.UUID | None = None
    try:
        local_now = datetime(2026, 9, 9, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        with SessionLocal() as db:
            source = Employee(
                name="Source " + suffix,
                email="source-digest-{}@example.invalid".format(suffix),
                role="Engineer",
                teams_user_id="source-digest-" + suffix,
                is_managed=True,
            )
            owner = Employee(
                name="Owner " + suffix,
                email="owner-digest-{}@example.invalid".format(suffix),
                role="Engineer",
                teams_user_id="owner-digest-" + suffix,
                is_managed=True,
            )
            db.add_all([source, owner])
            db.flush()
            employee_ids = [source.id, owner.id]
            source_chat = Conversation(
                employee_id=source.id,
                channel=ConversationChannel.TEAMS,
                conversation_type=ConversationType.DIRECT,
                started_at=local_now,
            )
            owner_chat = Conversation(
                employee_id=owner.id,
                channel=ConversationChannel.TEAMS,
                conversation_type=ConversationType.DIRECT,
                started_at=local_now,
            )
            db.add_all([source_chat, owner_chat])
            db.flush()
            conversation_ids = [source_chat.id, owner_chat.id]
            blocker = Blocker(
                blocked_employee_id=source.id,
                dependency_owner_id=owner.id,
                description="Backend deployment is needed",
                severity=BlockerSeverity.HIGH,
            )
            db.add(blocker)
            db.flush()
            blocker_id = blocker.id
            inbound = Message(
                conversation_id=source_chat.id,
                employee_id=source.id,
                direction=MessageDirection.INBOUND,
                sender_type=SenderType.EMPLOYEE,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                content="I need Owner's help for the backend deployment.",
            )
            acknowledgement = Message(
                conversation_id=source_chat.id,
                employee_id=source.id,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.AGENT,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                content="I’ll check with Owner and keep you posted.",
            )
            followup = Message(
                conversation_id=owner_chat.id,
                employee_id=owner.id,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.AGENT,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                content="When do you expect the deployment to be ready?",
            )
            db.add_all([inbound, acknowledgement, followup])
            db.flush()
            db.add(
                AgentRun(
                    inbound_message_id=inbound.id,
                    source_employee_id=source.id,
                    status=AgentRunStatus.COMPLETED,
                    analysis_type=AgentAnalysisType.BLOCKER,
                    blocker_id=blocker.id,
                    source_reply_message_id=acknowledgement.id,
                    dependency_message_id=followup.id,
                    processed_at=local_now,
                    state_applied=True,
                    decision_json={
                        "messages": [
                            {"kind": "acknowledgement"},
                            {"kind": "dependency_followup"},
                        ]
                    },
                )
            )
            db.commit()

            content = DailyAutomationService._daily_digest_content(db, local_now)

            assert "Agent handling today:" in content
            assert "recorded blocker: Backend deployment is needed" in content
            assert "asked Owner for an ETA" in content
            assert "acknowledged the update" in content
    finally:
        with SessionLocal() as db:
            if employee_ids:
                db.execute(delete(AgentRun).where(AgentRun.source_employee_id.in_(employee_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if conversation_ids:
                db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()


def test_operator_api_guard_leaves_graph_webhook_public(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "test-v1-operator-token")
    monkeypatch.setenv("MICROSOFT_WEBHOOK_BASE_URL", "https://example.ngrok.app")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        denied = client.post(
            "/api/v1/employees",
            json={
                "name": "Unauthorized",
                "email": "unauthorized@example.invalid",
                "role": "Engineer",
            },
        )
        assert denied.status_code == 401
        allowed = client.get(
            "/api/v1/employees",
            headers={"X-Manager-Operator-Token": "test-v1-operator-token"},
        )
        assert allowed.status_code == 200
        webhook = client.post("/api/v1/microsoft/teams/webhook", json={"value": []})
        assert webhook.status_code == 202
    finally:
        monkeypatch.setenv("OPERATOR_API_TOKEN", "")
        monkeypatch.setenv("MICROSOFT_WEBHOOK_BASE_URL", "")
        get_settings.cache_clear()


def test_sent_digest_is_persisted_and_retrievable() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    action_id: uuid.UUID | None = None
    try:
        with SessionLocal() as db:
            manager = Employee(
                name="Digest Manager " + suffix,
                email="digest-manager-{}@example.invalid".format(suffix),
                role="Manager",
            )
            db.add(manager)
            db.flush()
            employee_id = manager.id
            conversation = Conversation(
                employee_id=manager.id,
                channel=ConversationChannel.TEAMS,
                conversation_type=ConversationType.DIRECT,
                started_at=datetime.now(timezone.utc),
            )
            db.add(conversation)
            db.flush()
            conversation_id = conversation.id
            message = Message(
                conversation_id=conversation.id,
                employee_id=manager.id,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.AGENT,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                content="Daily manager digest\nResponded: 1/1",
            )
            db.add(message)
            db.flush()
            message_id = message.id
            action = AutomationAction(
                action_type=AutomationActionType.DAILY_DIGEST,
                status=AutomationActionStatus.DELIVERED,
                idempotency_key="digest-retrieval-" + suffix,
                employee_id=manager.id,
                message_id=message.id,
                executed_at=datetime.now(timezone.utc),
            )
            db.add(action)
            db.commit()
            action_id = action.id
            digests = DailyAutomationService.list_daily_digests(db)
            assert any(
                item.id == action.id
                and item.message is not None
                and item.message.content == "Daily manager digest\nResponded: 1/1"
                for item in digests
            )
        client = TestClient(app)
        response = client.get("/api/v1/microsoft/automation/digests")
        assert response.status_code == 200
        assert any(item["id"] == str(action_id) for item in response.json())
    finally:
        with SessionLocal() as db:
            if action_id is not None:
                db.execute(delete(AutomationAction).where(AutomationAction.id == action_id))
            if message_id is not None:
                db.execute(delete(Message).where(Message.id == message_id))
            if conversation_id is not None:
                db.execute(delete(Conversation).where(Conversation.id == conversation_id))
            if employee_id is not None:
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
