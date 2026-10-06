"""Regression scenarios use isolated PostgreSQL transactions and no live sends."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.management_agent import ManagementAgent
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (Employee, EmployeeAlias, Conversation, Message, Blocker, Commitment,
                       DailyUpdate, AgentRun, AutomationAction, Task)
from app.models.enums import (ConversationChannel, ConversationType, MessageDirection, SenderType,
    MessageDeliveryStatus, BlockerStatus, CommitmentStatus, AgentRunStatus,
    AutomationActionType, AutomationActionStatus, ActivityEventType, TaskStatus)
from app.models.memory import ActivityEvent
from app.models.response_state import ConversationQuestion
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.schemas.response_decision import ResponseDecision, IssueDecision, OutgoingDecision
from app.services.blocker_service import BlockerService
from app.services.microsoft_service import MicrosoftService
from app.services.response_service import ResponseService
from app.services.response_recovery_service import ResponseRecoveryService
from app.services.automation_service import DailyAutomationService
from app.services.errors import ExternalServiceError

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")


@pytest.fixture
def scenario(monkeypatch):
    with SessionLocal().get_bind().connect() as connection:
        outer = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        people, chats, sent = [], {}, []
        suffix = uuid.uuid4().hex[:8]
        for name in ("Source", "OwnerA", "OwnerB", "Unrelated"):
            person = Employee(name=name + suffix + " (dummy)", email=name + suffix + "@example.invalid",
                              role="Engineer", is_managed=True, teams_user_id=name + suffix)
            db.add(person); db.flush(); people.append(person)
            chat = Conversation(employee_id=person.id, channel=ConversationChannel.TEAMS,
                                conversation_type=ConversationType.DIRECT, started_at=datetime.now(timezone.utc))
            db.add(chat); db.flush(); chats[person.id] = chat
        def message(person, content, direction=MessageDirection.INBOUND, reply_to=None):
            item = Message(conversation_id=chats[person.id].id, employee_id=person.id,
                direction=direction, sender_type=SenderType.EMPLOYEE if direction == MessageDirection.INBOUND else SenderType.AGENT,
                delivery_status=MessageDeliveryStatus.DELIVERED, content=content,
                external_message_id=uuid.uuid4().hex, reply_to_external_id=reply_to,
                created_at=datetime.now(timezone.utc))
            db.add(item); db.flush(); return item
        def send(_db, recipient, content):
            item = message(recipient, content, MessageDirection.OUTBOUND)
            sent.append(item)
            return item
        monkeypatch.setattr(MicrosoftService, "send_management_message", send)
        active_run = SimpleNamespace(target_employee_ids=[str(person.id) for person in people])
        monkeypatch.setattr(MicrosoftService, "active_run", staticmethod(lambda _db: active_run))
        data = SimpleNamespace(db=db, people=people, chats=chats, sent=sent, message=message)
        yield data
        db.close()
        outer.rollback()


def decision(*, issues=None, messages=None, **kwargs):
    return ResponseDecision(should_respond=bool(messages), response_type="status_update" if messages else "no_response",
        reason="Scenario facts only", confidence=.96, needs_clarification=False,
        issues=issues or [], messages=messages or [], **kwargs)


def run(s, monkeypatch, inbound, result):
    captured = {}
    def analyze(context, message):
        captured.update(context)
        return result
    monkeypatch.setattr(ResponseService, "decide", staticmethod(analyze))
    output = ManagementAgent.process_message(s.db, str(inbound.id))
    assert output.status == AgentRunStatus.COMPLETED, output.failure_reason
    return output, captured


@pytest.mark.parametrize("content", ["I'm continuing the UI changes today.", "Deployment", "Everything is on track, nothing blocked"])
def test_progress_and_short_work_updates_do_not_invent_dependencies(scenario, monkeypatch, content):
    s = scenario; person = s.people[0]
    inbound = s.message(person, content)
    result = decision(today_summary=content, explicitly_no_blockers="nothing blocked" in content,
                      messages=[OutgoingDecision(recipient_id=person.id, kind="acknowledgement", text="Thanks, noted.")])
    run(s, monkeypatch, inbound, result)
    update = s.db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == person.id))
    assert update.today_summary == content
    assert not s.db.scalar(select(Blocker.id).where(Blocker.blocked_employee_id == person.id))
    assert len(s.sent) == 1 and "dependency" not in s.sent[0].content


def test_stale_issue_hallucination_is_reduced_to_safe_work_update(scenario, monkeypatch):
    s = scenario; person = s.people[0]; unrelated = s.people[1]
    content = "I am working on displaying the helper bot query and response in super admin."
    stale_id = uuid.uuid4()
    invalid = decision(
        today_summary="Old database blocker incorrectly revived",
        issues=[IssueDecision(
            key="stale", blocker_id=stale_id, operation="report_blocker",
            description="Old database deployment blocker", evidence=content,
            dependency_owner_ids=[unrelated.id],
        )],
        messages=[OutgoingDecision(
            recipient_id=unrelated.id, issue_key="stale", kind="dependency_followup",
            text="Please send an ETA.", awaiting_field="eta",
        )],
    )
    inbound = s.message(person, content)
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *_: invalid))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *_: invalid))

    output = ManagementAgent.process_message(s.db, str(inbound.id))
    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["issues"] == []
    assert output.decision_json["today_summary"] == content
    assert len(s.sent) == 1
    assert s.sent[0].employee_id == person.id
    assert "noted your update" in s.sent[0].content
    assert not s.db.scalar(select(Blocker.id).where(Blocker.blocked_employee_id == person.id))


def test_unlinked_eta_hallucination_is_reduced_to_safe_work_update(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    content = "I am working on displaying the helper bot query and response in super admin."
    invalid = decision(
        issues=[IssueDecision(
            key="invented-eta", operation="eta", blocker_id=None,
            description="Awaiting an ETA", evidence=content,
            dependency_owner_ids=[person.id],
        )],
        messages=[OutgoingDecision(
            recipient_id=person.id, issue_key="invented-eta", kind="status_update",
            text="Please share an ETA.", awaiting_field="eta",
        )],
    )
    inbound = s.message(person, content)
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *_: invalid))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *_: invalid))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["issues"] == []
    assert output.decision_json["today_summary"] == content
    assert len(s.sent) == 1 and s.sent[0].employee_id == person.id


def test_courtesy_only_reply_without_pending_question_is_ignored(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "Thanks for the update")
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("LLM must not be called"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["response_type"] == "no_response"
    assert output.state_applied is True
    assert not s.sent


def test_plain_work_update_bypasses_llm_and_old_issue_memory(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    content = "I am working on displaying the helper bot query and response in super admin."
    inbound = s.message(person, content)
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("LLM must not be called"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["issues"] == []
    assert output.decision_json["today_summary"] == content
    assert len(s.sent) == 1 and s.sent[0].employee_id == person.id
    assert output.attempt_count == 1


def test_unknown_owner_blocker_asks_only_source_and_ignores_stale_owner(scenario, monkeypatch):
    s = scenario; source, stale_owner = s.people[:2]
    BlockerService.create(s.db, BlockerCreate(
        blocked_employee_id=source.id,
        description="Old unrelated API blocker",
        dependency_owner_ids=[stale_owner.id],
    ))
    content = ("I’m blocked on the dummy deployment test because the API response format "
               "is missing. I don’t know who owns it.")
    inbound = s.message(source, content)
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("LLM must not be called"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert len(s.sent) == 1
    assert s.sent[0].employee_id == source.id
    assert "who should i follow up with" in s.sent[0].content.casefold()
    created = s.db.get(Blocker, output.blocker_id)
    assert created.description == content
    assert created.dependency_owner_ids == []


def test_failed_reply_is_recovered_automatically_once_due(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "I am working on the billing screen.")
    inbound.created_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    run_record = AgentRun(
        inbound_message_id=inbound.id,
        source_employee_id=person.id,
        status=AgentRunStatus.FAILED,
        attempt_count=1,
        policy_version=get_settings().response_policy_version,
        last_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    s.db.add(run_record); s.db.flush()
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("plain update must bypass LLM"))))

    processed = ResponseRecoveryService.process_due(s.db, now=datetime.now(timezone.utc), limit=1)

    s.db.refresh(run_record)
    assert processed == 1
    assert run_record.status == AgentRunStatus.COMPLETED
    assert run_record.attempt_count == 2


def test_delivery_failure_does_not_apply_state_and_retry_finishes_same_plan(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    inbound = s.message(
        source,
        f"I’m blocked waiting for {owner.name} to send the deployment manifest.",
    )
    calls = []

    def fail_owner(_db, recipient, content):
        calls.append(recipient.id)
        if recipient.id == owner.id:
            raise ExternalServiceError("simulated Graph failure")
        item = s.message(recipient, content, MessageDirection.OUTBOUND)
        s.sent.append(item)
        return item

    monkeypatch.setattr(MicrosoftService, "send_management_message", fail_owner)
    first = ManagementAgent.process_message(s.db, str(inbound.id))

    assert first.status == AgentRunStatus.FAILED
    assert first.state_applied is False
    assert first.blocker_id is None
    assert not s.db.scalar(select(Blocker.id).where(Blocker.blocked_employee_id == source.id))
    assert not s.db.scalar(select(DailyUpdate.id).where(DailyUpdate.employee_id == source.id))

    def succeed(_db, recipient, content):
        item = s.message(recipient, content, MessageDirection.OUTBOUND)
        s.sent.append(item)
        return item

    monkeypatch.setattr(MicrosoftService, "send_management_message", succeed)
    second = ManagementAgent.process_message(s.db, str(inbound.id))

    assert second.status == AgentRunStatus.COMPLETED
    assert second.state_applied is True
    assert second.blocker_id is not None
    assert calls.count(source.id) == 1
    assert len([item for item in s.sent if item.employee_id == source.id]) == 1
    assert len([item for item in s.sent if item.employee_id == owner.id]) == 1


def test_standalone_timed_promise_becomes_commitment_without_llm(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "I will finish the validation report tomorrow at 4 PM.")
    reference = datetime.now(ZoneInfo(get_settings().manager_timezone)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    inbound.external_created_at = reference
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("literal promise must bypass LLM"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    promise = s.db.scalar(select(Commitment).where(
        Commitment.source_message_id == inbound.id,
        Commitment.blocker_id.is_(None),
    ))
    assert promise is not None
    assert promise.deadline == reference.replace(hour=16) + timedelta(days=1)
    assert len(s.sent) == 1 and s.sent[0].employee_id == person.id
    ManagementAgent.process_message(s.db, str(inbound.id), retry_completed=True)
    assert len(list(s.db.scalars(select(Commitment).where(
        Commitment.source_message_id == inbound.id
    )))) == 1


def test_standalone_question_does_not_replace_daily_work_state(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "Can we review the validation plan together?")
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("ordinary question must bypass LLM"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert s.db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == person.id)) is None
    assert output.decision_json["intent"] == "question"
    assert len(s.sent) == 1 and s.sent[0].employee_id == person.id


def test_completion_does_not_answer_immediately_previous_owner_question(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    question_message = s.message(
        person, "Who owns the API dependency?", MessageDirection.OUTBOUND
    )
    s.db.add(ConversationQuestion(
        conversation_id=question_message.conversation_id,
        message_id=question_message.id,
        awaiting_field="owner",
    ))
    s.db.flush()
    inbound = s.message(person, "I completed deployment validation.")
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("standalone completion must bypass LLM"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.context_json["message_focus"] == "standalone"
    assert output.context_json["unresolved_questions"] == []
    assert output.decision_json["issues"] == []


@pytest.mark.parametrize("owner_count", [1, 2])
def test_one_or_multiple_owners_are_stored_and_contacted_separately(scenario, monkeypatch, owner_count):
    s = scenario; person = s.people[0]; owners = s.people[1:owner_count+1]
    content = "I'm blocked waiting for " + " and ".join(owner.name for owner in owners) + " to send the API changes."
    issue = IssueDecision(key="api", operation="report_blocker", description="API changes", evidence=content,
                          dependency_owner_ids=[p.id for p in owners])
    messages = [OutgoingDecision(recipient_id=person.id, kind="acknowledgement", issue_key="api", text="I'll check with them and keep you posted.")]
    messages += [OutgoingDecision(recipient_id=p.id, kind="dependency_followup", issue_key="api", text="The API changes are needed. When will they be ready?", awaiting_field="eta") for p in owners]
    inbound = s.message(person, content)
    output, _ = run(s, monkeypatch, inbound, decision(issues=[issue], messages=messages))
    blocker = s.db.get(Blocker, output.blocker_id)
    assert set(blocker.dependency_owner_ids) == {p.id for p in owners}
    assert len(s.sent) == owner_count + 1
    assert all("(dummy)" not in msg.content for msg in s.sent)
    assert len(list(s.db.scalars(select(ConversationQuestion).where(ConversationQuestion.blocker_id == blocker.id)))) == owner_count
    # Webhook replay does not send or re-analyze a completed message.
    ManagementAgent.process_message(s.db, str(inbound.id), retry_completed=True)
    assert len(s.sent) == owner_count + 1


def test_exact_repeated_blocker_reuses_issue_without_duplicate_messages(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    content = f"I'm blocked waiting for {owner.name} to send the exact retry fixture."
    first = s.message(source, content)
    second = s.message(source, content)
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("literal blockers must bypass LLM"))))

    first_run = ManagementAgent.process_message(s.db, str(first.id))
    second_run = ManagementAgent.process_message(s.db, str(second.id))

    assert first_run.status == second_run.status == AgentRunStatus.COMPLETED
    assert first_run.blocker_id == second_run.blocker_id
    assert len(s.sent) == 2
    assert {item.employee_id for item in s.sent} == {source.id, owner.id}


def test_quoted_eta_targets_correct_issue_with_two_outstanding_questions(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    blockers, questions = [], []
    for description in ["Database changes", "Admin preference API"]:
        blocker = BlockerService.create(s.db, BlockerCreate(blocked_employee_id=source.id,
            dependency_owner_ids=[owner.id], description=description))
        request = s.message(owner, "When will " + description + " be ready?", MessageDirection.OUTBOUND)
        question = ConversationQuestion(conversation_id=request.conversation_id, message_id=request.id,
                                        blocker_id=blocker.id, awaiting_field="eta")
        s.db.add(question); s.db.flush(); questions.append(question); blockers.append(blocker)
    target = s.db.get(Message, questions[0].message_id)
    inbound = s.message(owner, "tomorrow at 4 PM", reply_to=target.external_message_id)
    eta = datetime.now(timezone.utc) + timedelta(days=1)
    issue = IssueDecision(key="db", blocker_id=blockers[0].id, operation="eta", description="Database changes", evidence=inbound.content, deadline=eta)
    _, context = run(s, monkeypatch, inbound, decision(issues=[issue], answered_question_ids=[questions[0].id], messages=[
        OutgoingDecision(recipient_id=owner.id, issue_key="db", kind="acknowledgement", text="Thanks, I'll track that ETA."),
        OutgoingDecision(recipient_id=source.id, issue_key="db", kind="status_update", text="The database changes are expected tomorrow at 4 PM.")]))
    assert context["quoted_message_id"] == str(target.id)
    promises = list(s.db.scalars(select(Commitment).where(Commitment.blocker_id.in_([b.id for b in blockers]))))
    assert len(promises) == 1 and promises[0].blocker_id == blockers[0].id
    assert questions[0].answered_by_message_id == inbound.id and questions[1].answered_at is None
    assert len(s.sent) == 2


def test_new_issue_does_not_reassign_or_forward_old_description(scenario, monkeypatch):
    s = scenario; source, old_owner, new_owner = s.people[:3]
    old = BlockerService.create(s.db, BlockerCreate(blocked_employee_id=source.id,
        dependency_owner_ids=[old_owner.id], description="Old chatbot response format"))
    text_value = "I need attachment changes from " + new_owner.name
    inbound = s.message(source, text_value)
    issue = IssueDecision(key="attachment", operation="report_blocker", description="Attachment changes",
                          dependency_owner_ids=[new_owner.id], evidence=text_value)
    output, _ = run(s, monkeypatch, inbound, decision(issues=[issue], messages=[OutgoingDecision(
        recipient_id=new_owner.id, issue_key="attachment", kind="dependency_followup",
        text="The attachment changes are needed to finish the UI. When might they be ready?", awaiting_field="eta")]))
    assert output.blocker_id != old.id and old.dependency_owner_ids == [old_owner.id]
    assert "response format" not in s.sent[0].content


def test_explicit_owner_correction_preserves_history(scenario, monkeypatch):
    s = scenario; source, old_owner, new_owner = s.people[:3]
    blocker = BlockerService.create(s.db, BlockerCreate(blocked_employee_id=source.id,
        dependency_owner_ids=[old_owner.id], description="API changes"))
    inbound = s.message(source, new_owner.name + " owns this API instead")
    issue = IssueDecision(key="api", operation="set_owners", blocker_id=blocker.id,
        description=blocker.description, dependency_owner_ids=[new_owner.id], evidence=inbound.content)
    run(s, monkeypatch, inbound, decision(issues=[issue], messages=[OutgoingDecision(
        recipient_id=new_owner.id, issue_key="api", kind="dependency_followup", text="When will the API changes be ready?", awaiting_field="eta")]))
    assert blocker.dependency_owner_ids == [new_owner.id]
    events = list(s.db.scalars(select(ActivityEvent).where(ActivityEvent.entity_id == blocker.id,
        ActivityEvent.event_type == ActivityEventType.BLOCKER_DEPENDENCY_OWNER_CHANGED)))
    assert events[-1].metadata_json["previous"]["dependency_owner_ids"] == [str(old_owner.id)]
    assert events[-1].metadata_json["new"]["dependency_owner_ids"] == [str(new_owner.id)]
    assert any(not link.is_active and link.employee_id == old_owner.id for link in blocker.dependencies)


def test_quoted_owner_handoff_restores_issue_and_contacts_new_owner(scenario, monkeypatch):
    s = scenario; source, old_owner, new_owner = s.people[:3]
    blocker = BlockerService.create(s.db, BlockerCreate(
        blocked_employee_id=source.id,
        dependency_owner_ids=[old_owner.id],
        description="Frontend permissions changes needed for current work",
    ))
    quoted = s.message(source, "There are no pending changes from the previous owner.",
                       MessageDirection.OUTBOUND)
    question = ConversationQuestion(
        conversation_id=quoted.conversation_id,
        message_id=quoted.id,
        blocker_id=blocker.id,
        awaiting_field="eta",
    )
    s.db.add(question); s.db.flush()
    inbound = s.message(source, "The frontend permissions task is owned by " + new_owner.name,
                        reply_to=quoted.external_message_id)
    incomplete = decision(issues=[IssueDecision(
        key="permissions", operation="set_owners", description="Reassign permissions task",
        dependency_owner_ids=[old_owner.id, new_owner.id], evidence=inbound.content,
    )], messages=[OutgoingDecision(
        recipient_id=source.id, issue_key="permissions", kind="acknowledgement",
        text="Thanks, I’ve noted the new owner.",
        awaiting_field="owner",
    )])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: incomplete))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: incomplete))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["issues"][0]["blocker_id"] == str(blocker.id)
    assert blocker.dependency_owner_ids == [new_owner.id]
    assert question.answered_by_message_id == inbound.id
    assert {(item.employee_id, item.direction) for item in s.sent} == {
        (source.id, MessageDirection.OUTBOUND), (new_owner.id, MessageDirection.OUTBOUND)}


def test_existing_issue_update_does_not_create_duplicate(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    blocker = BlockerService.create(s.db, BlockerCreate(blocked_employee_id=source.id,
        dependency_owner_ids=[owner.id], description="API changes"))
    inbound = s.message(source, "The API is still pending with " + owner.name)
    run(s, monkeypatch, inbound, decision(issues=[IssueDecision(key="api", blocker_id=blocker.id,
        operation="report_blocker", description=blocker.description, dependency_owner_ids=[owner.id], evidence=inbound.content)]))
    assert len(list(s.db.scalars(select(Blocker).where(Blocker.blocked_employee_id == source.id)))) == 1


def test_done_resolves_only_speaking_owners_contribution(scenario, monkeypatch):
    s = scenario; source, first, second = s.people[:3]
    blocker = BlockerService.create(s.db, BlockerCreate(blocked_employee_id=source.id,
        dependency_owner_ids=[first.id, second.id], description="API changes"))
    for person in [first, second]:
        question_message = s.message(person, "Are your API changes delivered?", MessageDirection.OUTBOUND)
        question = ConversationQuestion(conversation_id=question_message.conversation_id, message_id=question_message.id,
                                        blocker_id=blocker.id, awaiting_field="completion")
        s.db.add(question); s.db.flush()
        inbound = s.message(person, "done", reply_to=question_message.external_message_id)
        run(s, monkeypatch, inbound, decision(issues=[IssueDecision(key="api", blocker_id=blocker.id,
            operation="delivered", description="API changes", evidence="done")], answered_question_ids=[question.id],
            messages=[
                OutgoingDecision(recipient_id=person.id, issue_key="api", kind="acknowledgement",
                                 text="Thanks, I’ve marked your part as delivered."),
                OutgoingDecision(recipient_id=source.id, issue_key="api", kind="status_update",
                                 text="One of the API contributions has now been delivered."),
            ]))
        assert blocker.status == (BlockerStatus.OPEN if person.id == first.id else BlockerStatus.RESOLVED)


def test_valid_delivery_with_missing_ack_gets_safe_two_person_messages(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    blocker = BlockerService.create(s.db, BlockerCreate(
        blocked_employee_id=source.id,
        dependency_owner_ids=[owner.id],
        description="Role API changes",
    ))
    request = s.message(owner, "Are the Role API changes complete?", MessageDirection.OUTBOUND)
    question = ConversationQuestion(
        conversation_id=request.conversation_id,
        message_id=request.id,
        blocker_id=blocker.id,
        awaiting_field="completion",
    )
    s.db.add(question); s.db.flush()
    inbound = s.message(owner, "It is completed now and I shared the details",
                        reply_to=request.external_message_id)
    incomplete = decision(issues=[IssueDecision(
        key="role-api", blocker_id=blocker.id, operation="delivered",
        description=blocker.description, evidence=inbound.content,
    )], messages=[OutgoingDecision(
        recipient_id=source.id, issue_key="role-api", kind="status_update",
        text="The role API changes are complete and the details have been shared.",
        awaiting_field="eta",
    )])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: incomplete))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: incomplete))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert blocker.status == BlockerStatus.RESOLVED
    assert output.context_json["validation_feedback"] == (
        "Acknowledgements and status updates cannot open a pending question")
    assert {(item.employee_id, item.direction) for item in s.sent} == {
        (owner.id, MessageDirection.OUTBOUND), (source.id, MessageDirection.OUTBOUND)}
    assert any("your part is complete" in item.content.casefold() for item in s.sent
               if item.employee_id == owner.id)


def test_done_can_complete_owned_task(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    task = Task(owner_id=person.id, title="API", expected_outcome="Staging endpoint working")
    s.db.add(task); s.db.flush()
    qmsg = s.message(person, "Is the staging endpoint complete?", MessageDirection.OUTBOUND)
    q = ConversationQuestion(conversation_id=qmsg.conversation_id, message_id=qmsg.id, task_id=task.id, awaiting_field="completion")
    s.db.add(q); s.db.flush()
    inbound = s.message(person, "done", reply_to=qmsg.external_message_id)
    run(s, monkeypatch, inbound, decision(issues=[IssueDecision(key="task", task_id=task.id,
        operation="complete_task", description=task.title, evidence="done")], answered_question_ids=[q.id]))
    assert task.status == TaskStatus.DONE and task.completed_at is not None


def test_received_but_incomplete_reply_suppresses_no_response_reminder(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    local = datetime.now(ZoneInfo(get_settings().manager_timezone)).replace(hour=13, minute=0)
    checkin_time = local.replace(hour=12, minute=50)
    monkeypatch.setattr(DailyAutomationService, "_managed_employees", staticmethod(lambda db: [person]))
    monkeypatch.setattr(DailyAutomationService, "_daily_checkin_key", staticmethod(lambda *args: "dummy-checkin"))
    s.db.add(AutomationAction(action_type=AutomationActionType.DAILY_CHECKIN, status=AutomationActionStatus.DELIVERED,
        idempotency_key="dummy-checkin", employee_id=person.id, executed_at=checkin_time))
    inbound = s.message(person, "Deployment")
    inbound.external_created_at = checkin_time + timedelta(minutes=1)
    s.db.flush()
    assert DailyAutomationService.send_no_response_followups(s.db, local) == 0
    assert not s.sent


def test_fabricated_owner_is_ignored_and_source_gets_safe_clarification(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    inbound = s.message(source, "Waiting for the API team")
    result = decision(issues=[IssueDecision(key="api", operation="report_blocker", description="API changes",
        dependency_owner_ids=[owner.id], evidence=inbound.content)])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: result))
    output = ManagementAgent.process_message(s.db, str(inbound.id))
    assert output.status == AgentRunStatus.COMPLETED
    blocker = s.db.get(Blocker, output.blocker_id)
    assert blocker is not None and blocker.dependency_owner_ids == []
    assert len(s.sent) == 1 and s.sent[0].employee_id == source.id


def test_explicit_alias_resolves_owner_without_fuzzy_guessing(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    alias = "Atharva" + uuid.uuid4().hex[:6]
    owner.alias_records.append(EmployeeAlias(alias=alias, normalized_alias=alias.casefold()))
    s.db.flush()
    inbound = s.message(source, "I'm blocked waiting for {} to send the endpoint.".format(alias))
    # A standalone blocker report naming a known alias is handled by the
    # deterministic new_blocker_update fast path (owner resolved from the same
    # alias/name matching validate() enforces), so ResponseService.decide is
    # never reached here; it stays monkeypatched only to prove that.
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("LLM must not be called"))))
    output = ManagementAgent.process_message(s.db, str(inbound.id))
    assert output.status == AgentRunStatus.COMPLETED, output.failure_reason
    context = output.context_json
    assert context["mentioned_people"] == [{"id": str(owner.id), "name": owner.name, "matched_text": alias}]
    assert next(person for person in context["people"] if person["id"] == str(owner.id))["aliases"] == [alias]
    assert {item.employee_id for item in s.sent} == {source.id, owner.id}
    owner_message = next(item for item in s.sent if item.employee_id == owner.id)
    assert "when do you expect your part to be ready" in owner_message.content.casefold()


def test_named_help_request_creates_blocker_but_does_not_contact_owner_outside_active_run(scenario, monkeypatch):
    """A natural blocker report must not silently expand the run's message scope."""

    s = scenario
    source, owner = s.people[:2]
    monkeypatch.setattr(
        MicrosoftService,
        "active_run",
        staticmethod(lambda _db: SimpleNamespace(target_employee_ids=[str(source.id)])),
    )
    inbound = s.message(source, "I need some help of {} for this backend deployment.".format(owner.name.split()[0]))
    monkeypatch.setattr(ResponseService, "decide", staticmethod(
        lambda *args: (_ for _ in ()).throw(AssertionError("literal blocker must bypass LLM"))))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED, output.failure_reason
    blocker = s.db.get(Blocker, output.blocker_id)
    assert blocker is not None and blocker.dependency_owner_ids == [owner.id]
    assert len(s.sent) == 1
    assert s.sent[0].employee_id == source.id
    assert "can't contact" in s.sent[0].content.casefold()


def test_unsafe_owner_proposal_falls_back_without_retrying_bad_decision(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    inbound = s.message(source, "Waiting for the API team")
    invalid = decision(issues=[IssueDecision(key="api", operation="report_blocker",
        description="API changes", dependency_owner_ids=[owner.id], evidence=inbound.content)])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: invalid))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: invalid))
    first = ManagementAgent.process_message(s.db, str(inbound.id))
    assert first.status == AgentRunStatus.COMPLETED and first.state_applied is True
    assert first.decision_json["issues"][0]["dependency_owner_ids"] == []
    assert len(s.sent) == 1


def test_invalid_eta_message_is_repaired_into_owner_ack_and_source_update(scenario, monkeypatch):
    s = scenario; source, owner = s.people[:2]
    blocker = BlockerService.create(s.db, BlockerCreate(
        blocked_employee_id=source.id,
        dependency_owner_ids=[owner.id],
        description="Role API changes",
    ))
    request = s.message(owner, "When will the role API changes be ready?", MessageDirection.OUTBOUND)
    question = ConversationQuestion(
        conversation_id=request.conversation_id,
        message_id=request.id,
        blocker_id=blocker.id,
        awaiting_field="eta",
    )
    s.db.add(question); s.db.flush()
    inbound = s.message(owner, "It is in the last stage and I will send it at 6:30 PM",
                        reply_to=request.external_message_id)
    message_time = datetime.now(ZoneInfo(get_settings().manager_timezone)).replace(
        hour=18, minute=15, second=0, microsecond=0)
    inbound.external_created_at = message_time
    deadline = message_time.replace(hour=18, minute=30)
    eta_without_deadline = IssueDecision(key="role-api", blocker_id=blocker.id, operation="eta",
        description=blocker.description, evidence=inbound.content)
    eta = IssueDecision(key="role-api", blocker_id=blocker.id, operation="eta",
        description=blocker.description, evidence=inbound.content, deadline=deadline)
    invalid = decision(issues=[eta_without_deadline], answered_question_ids=[question.id], messages=[OutgoingDecision(
        recipient_id=source.id, issue_key="role-api", kind="dependency_followup",
        text="The role API changes should be ready at 6:30 PM.", awaiting_field="eta")])
    corrected = decision(issues=[eta], answered_question_ids=[question.id], messages=[
        OutgoingDecision(recipient_id=owner.id, issue_key="role-api", kind="acknowledgement",
                         text="Thanks, noted for 6:30 PM."),
        OutgoingDecision(recipient_id=source.id, issue_key="role-api", kind="status_update",
                         text="The role API changes are in the final stage and should be ready by 6:30 PM."),
    ])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: invalid))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: corrected))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert (output.context_json.get("validation_feedback")
            or output.context_json.get("repair_validation_feedback")) == (
                "A dependency request must target an owner of that exact issue"
            )
    assert output.decision_json["messages"][0]["kind"] == "acknowledgement"
    promise = s.db.scalar(select(Commitment).where(Commitment.blocker_id == blocker.id))
    assert promise is not None and promise.employee_id == owner.id and promise.deadline == deadline
    assert question.answered_by_message_id == inbound.id
    assert {(item.employee_id, item.direction) for item in s.sent} == {
        (owner.id, MessageDirection.OUTBOUND), (source.id, MessageDirection.OUTBOUND)}


def test_unmapped_completion_is_repaired_into_daily_update(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "I have completed the chatbot editing feature and all my tasks")
    invalid = decision(issues=[IssueDecision(
        key="unknown-delivery", operation="delivered", description="Chatbot editing feature",
        evidence=inbound.content,
    )], messages=[OutgoingDecision(
        recipient_id=person.id, issue_key="unknown-delivery", kind="clarification",
        text="Which internal issue key does this complete?", awaiting_field="issue")])
    corrected = decision(completed_summary="Completed the chatbot editing feature and all assigned tasks",
        messages=[OutgoingDecision(recipient_id=person.id, kind="acknowledgement",
                                   text="Great, I’ve noted those tasks as completed.")])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: invalid))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: corrected))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    update = s.db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == person.id))
    assert update.completed_summary == inbound.content
    assert not s.db.scalar(select(Blocker.id).where(Blocker.blocked_employee_id == person.id))
    assert len(s.sent) == 1 and "issue key" not in s.sent[0].content.casefold()


def test_repeated_unmapped_delivery_proposal_falls_back_to_safe_update(scenario, monkeypatch):
    s = scenario; person = s.people[0]
    inbound = s.message(person, "BEAM Test will be dropped from the list.")
    unsupported = decision(issues=[
        IssueDecision(key="first", operation="delivered", description="BEAM Test removed",
                      evidence=inbound.content),
        IssueDecision(key="duplicate", operation="delivered", description="BEAM Test removed",
                      evidence=inbound.content),
    ], messages=[
        OutgoingDecision(recipient_id=person.id, issue_key="first", kind="acknowledgement",
                         text="Update captured."),
        OutgoingDecision(recipient_id=person.id, issue_key="duplicate", kind="acknowledgement",
                         text="Update captured."),
    ])
    monkeypatch.setattr(ResponseService, "decide", staticmethod(lambda *args: unsupported))
    monkeypatch.setattr(ResponseService, "repair", staticmethod(lambda *args: unsupported))

    output = ManagementAgent.process_message(s.db, str(inbound.id))

    assert output.status == AgentRunStatus.COMPLETED
    assert output.decision_json["issues"] == []
    update = s.db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == person.id))
    assert update.today_summary == inbound.content
    # This message carries no blocker/completion/commitment signal, so the
    # deterministic ordinary_conversation_update fast path handles it directly
    # and the mocked "unsupported delivery" decide()/repair() are never reached.
    assert len(s.sent) == 1 and "noted your update" in s.sent[0].content.casefold()


def test_legacy_self_dependency_is_preserved_but_excluded_from_decision_context(scenario):
    s = scenario; person = s.people[0]
    legacy = Blocker(
        blocked_employee_id=person.id,
        dependency_owner_id=person.id,
        description="Legacy self-owned dependency",
    )
    s.db.add(legacy); s.db.flush()
    inbound = s.message(person, "Here is an unrelated technical report")

    context = ResponseService.context(s.db, inbound, person)

    assert s.db.get(Blocker, legacy.id) is legacy
    assert str(legacy.id) not in {item["id"] for item in context["issues"]}
