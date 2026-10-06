import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import ModelPricing, Settings
from app.schemas.response_decision import IssueDecision, OutgoingDecision, ResponseDecision
from app.services.llm_service import LLMService, calculate_cost, strict_schema
from app.services.microsoft_service import MicrosoftService
from app.services.response_service import ResponseService


def test_cached_tokens_are_not_charged_twice():
    rates = ModelPricing(input=2, cached_input=0.5, output=8)
    costs = calculate_cost(
        {
            "prompt_tokens": 1000,
            "prompt_tokens_details": {"cached_tokens": 400},
            "completion_tokens": 200,
        },
        rates,
    )
    assert costs == (Decimal(".0014"), Decimal(".0016"), Decimal(".0030"))
    assert calculate_cost({}, rates) == (None, None, None)
    assert calculate_cost({"prompt_tokens": 1000, "completion_tokens": 20}, None) == (
        None,
        None,
        None,
    )


def test_strict_schema_requires_every_property_including_nested_objects():
    schema = strict_schema(ResponseDecision)
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    encoded = json.dumps(schema)
    for unsupported in ("maxLength", "minLength", "maxItems", "minimum", "maximum", "title"):
        assert '"{}"'.format(unsupported) not in encoded


def test_teams_quote_is_not_employee_evidence_and_reference_survives():
    remote = {
        "body": {
            "contentType": "html",
            "content": '<blockquote itemid="original-id">Who owns the dependency? Morgan?</blockquote><p>Nothing blocked, working on the UI.</p>',
        }
    }
    assert MicrosoftService._message_content(remote) == "Nothing blocked, working on the UI."
    reference, quote = MicrosoftService._reply_reference(remote)
    assert reference == "original-id" and "Morgan" in quote
    attached = {
        "body": {"contentType": "html", "content": "<p>Tomorrow at 4 PM</p>"},
        "attachments": [
            {"contentType": "messageReference", "content": json.dumps({"messageId": "first-issue"})}
        ],
    }
    assert MicrosoftService._reply_reference(attached)[0] == "first-issue"


@pytest.mark.parametrize("valid", [True, False])
def test_usage_is_saved_even_when_model_output_is_invalid(monkeypatch, valid):
    saved = []

    class UsageSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def add(self, item):
            saved.append(item)

        def commit(self):
            pass

    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        AZURE_OPENAI_ENDPOINT="https://test.openai.azure.com",
        AZURE_OPENAI_API_KEY="fake",
        AZURE_OPENAI_DEPLOYMENT="small",
        LLM_MODEL_PRICING={"model-version": {"input": 2, "cached_input": 0.5, "output": 8}},
    )
    monkeypatch.setattr("app.services.llm_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.llm_service.SessionLocal", UsageSession)
    result = {
        "should_respond": False,
        "response_type": "no_response",
        "reason": "Nothing outstanding",
        "confidence": 0.99,
        "needs_clarification": False,
    }

    def post(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "model": "model-version",
                "id": "request-123",
                "usage": {
                    "prompt_tokens": 1000,
                    "prompt_tokens_details": {"cached_tokens": 400},
                    "completion_tokens": 200,
                    "total_tokens": 1200,
                },
                "choices": [{"message": {"content": json.dumps(result) if valid else "invalid"}}],
            },
        )

    monkeypatch.setattr("app.services.llm_service.httpx.post", post)
    if valid:
        LLMService.complete(
            prompt="test", context={}, output_model=ResponseDecision, feature="test"
        )
    else:
        with pytest.raises(Exception):
            LLMService.complete(
                prompt="test", context={}, output_model=ResponseDecision, feature="test"
            )
    assert len(saved) == 1 and saved[0].model == "model-version"
    assert saved[0].estimated_total_cost_usd == Decimal(".003")
    assert saved[0].request_id == "request-123"
    assert saved[0].status == ("completed" if valid else "failed")


def test_llm_retries_a_timeout_then_returns_the_structured_decision(monkeypatch):
    saved = []

    class UsageSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def add(self, item):
            saved.append(item)

        def commit(self):
            pass

    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        AZURE_OPENAI_ENDPOINT="https://test.openai.azure.com",
        AZURE_OPENAI_API_KEY="fake",
        AZURE_OPENAI_DEPLOYMENT="small",
        AZURE_OPENAI_MAX_ATTEMPTS=2,
    )
    monkeypatch.setattr("app.services.llm_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.llm_service.SessionLocal", UsageSession)
    monkeypatch.setattr("app.services.llm_service.time.sleep", lambda _: None)
    calls = []
    output = {
        "should_respond": False,
        "response_type": "no_response",
        "reason": "Nothing outstanding",
        "confidence": 0.99,
        "needs_clarification": False,
    }

    def post(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow Azure response")
        return httpx.Response(
            200, json={"model": "small", "choices": [{"message": {"content": json.dumps(output)}}]}
        )

    monkeypatch.setattr("app.services.llm_service.httpx.post", post)
    result = LLMService.complete(
        prompt="test", context={}, output_model=ResponseDecision, feature="test"
    )
    assert result.should_respond is False
    assert len(calls) == 2
    assert calls[0]["timeout"].read == 25.0
    assert len(saved) == 1 and saved[0].status == "completed"


def test_explicit_no_blocker_fallback_discards_invented_dependency_actions():
    employee_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    message = SimpleNamespace(content="I own all tasks, ETA Monday 12 PM, no dependency or blocker")
    employee = SimpleNamespace(id=employee_id)
    decision = ResponseDecision(
        should_respond=True,
        response_type="dependency_followup",
        reason="Incorrect model proposal",
        confidence=0.9,
        needs_clarification=False,
        explicitly_no_blockers=True,
        issues=[
            IssueDecision(
                key="bad-dependency",
                operation="report_blocker",
                description="Incorrect dependency",
                dependency_owner_ids=[owner_id],
                evidence="no dependency or blocker",
            )
        ],
        messages=[
            OutgoingDecision(
                recipient_id=owner_id,
                issue_key="bad-dependency",
                kind="dependency_followup",
                text="When will this be ready?",
            )
        ],
    )
    fallback = ResponseService.safe_no_blocker_fallback(
        message,
        employee,
        decision,
        "A no-blocker update cannot introduce dependency actions",
    )
    assert fallback is not None
    assert fallback.explicitly_no_blockers is True
    assert fallback.issues == []
    assert len(fallback.messages) == 1
    assert fallback.messages[0].recipient_id == employee_id


def test_explicit_no_blocker_update_does_not_call_the_model():
    employee_id = uuid.uuid4()
    message = SimpleNamespace(content="I own all tasks, ETA Monday 12 PM, no dependency or blocker")
    employee = SimpleNamespace(id=employee_id)
    decision = ResponseService.explicit_no_blocker_update(
        {"unresolved_questions": []}, message, employee
    )
    assert decision is not None
    assert decision.explicitly_no_blockers is True
    assert decision.issues == []
    assert decision.messages[0].recipient_id == employee_id


def test_standalone_no_blocker_update_ignores_old_unanswered_question():
    employee_id = uuid.uuid4()
    message = SimpleNamespace(
        content="I own the test task, ETA Monday 12 PM, no dependency or blocker"
    )
    employee = SimpleNamespace(id=employee_id)
    decision = ResponseService.explicit_no_blocker_update(
        {
            "unresolved_questions": [{"blocker_id": str(uuid.uuid4())}],
            "quoted_message_id": None,
        },
        message,
        employee,
    )
    assert decision is not None
    assert decision.explicitly_no_blockers is True


def test_plain_standalone_work_update_ignores_old_unanswered_question():
    employee_id = uuid.uuid4()
    message = SimpleNamespace(
        content=(
            "AUTONOMY TEST 01: I am working on validating the deployment "
            "checklist and reviewing the release configuration."
        )
    )
    employee = SimpleNamespace(id=employee_id)
    stale_question = {"id": str(uuid.uuid4()), "blocker_id": str(uuid.uuid4())}
    decision = ResponseService.plain_work_update(
        {"unresolved_questions": [stale_question], "quoted_message_id": None},
        message,
        employee,
    )
    assert decision is not None
    assert decision.issues == []
    assert decision.messages[0].recipient_id == employee_id


def test_plain_quoted_reply_still_uses_issue_scoped_decision_path():
    employee_id = uuid.uuid4()
    message = SimpleNamespace(content="I am working on validating the deployment checklist")
    employee = SimpleNamespace(id=employee_id)
    decision = ResponseService.plain_work_update(
        {
            "unresolved_questions": [{"id": str(uuid.uuid4())}],
            "quoted_message_id": "outbound-message-id",
        },
        message,
        employee,
    )
    assert decision is None


def test_courtesy_only_message_stays_silent_despite_old_questions():
    decision = ResponseService.non_actionable_acknowledgement(
        {"unresolved_questions": [{"id": str(uuid.uuid4())}]},
        SimpleNamespace(content="Okay, thanks."),
    )
    assert decision is not None
    assert decision.should_respond is False
    assert decision.messages == []


def test_completed_and_current_work_bypasses_stale_issue_context():
    employee_id = uuid.uuid4()
    message = SimpleNamespace(
        content=(
            "I’m working on the deployment flow. I’ve finished the checklist structure, "
            "and now I’m testing the validation steps."
        )
    )
    decision = ResponseService.standalone_progress_update(
        {
            "quoted_message_id": None,
            "unresolved_questions": [{"blocker_id": str(uuid.uuid4())}],
            "issues": [{"id": str(uuid.uuid4()), "description": "Old unrelated blocker"}],
        },
        message,
        SimpleNamespace(id=employee_id),
    )
    assert decision is not None
    assert decision.issues == []
    assert decision.messages[0].recipient_id == employee_id
    assert "finished the checklist structure" in decision.completed_summary
    assert "testing the validation steps" not in decision.completed_summary
    assert "testing the validation steps" in decision.today_summary


def test_progress_classifier_does_not_swallow_a_real_blocker():
    decision = ResponseService.standalone_progress_update(
        {"quoted_message_id": None, "unresolved_questions": []},
        SimpleNamespace(
            content=(
                "I finished the checklist, and now I’m testing validation but I’m blocked "
                "because the API format is missing."
            )
        ),
        SimpleNamespace(id=uuid.uuid4()),
    )
    assert decision is None


def test_response_intent_is_derived_from_outgoing_messages():
    employee_id = uuid.uuid4()
    decision = ResponseDecision(
        should_respond=False,
        response_type="no_response",
        reason="Model bookkeeping mismatch",
        confidence=0.9,
        needs_clarification=False,
        messages=[
            OutgoingDecision(
                recipient_id=employee_id,
                kind="acknowledgement",
                text="Thanks, noted.",
            )
        ],
    )
    normalized = ResponseService.normalize_response_intent(decision)
    assert normalized.should_respond is True
    assert normalized.response_type == "acknowledgement"


def test_unknown_owner_blocker_never_inherits_a_historical_owner():
    employee_id = uuid.uuid4()
    old_owner_id = uuid.uuid4()
    content = (
        "I’m blocked on the dummy deployment test because the API response format "
        "is missing. I don’t know who owns it."
    )
    decision = ResponseService.unknown_owner_blocker(
        {
            "quoted_message_id": None,
            "issues": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Old blocker",
                    "dependency_owner_ids": [str(old_owner_id)],
                }
            ],
        },
        SimpleNamespace(content=content),
        SimpleNamespace(id=employee_id),
    )
    assert decision is not None
    assert len(decision.issues) == 1
    assert decision.issues[0].blocker_id is None
    assert decision.issues[0].dependency_owner_ids == []
    assert len(decision.messages) == 1
    assert decision.messages[0].recipient_id == employee_id
    assert decision.messages[0].kind == "clarification"


def test_quoted_unknown_owner_followup_keeps_question_open():
    employee_id = uuid.uuid4()
    question_id = uuid.uuid4()
    outbound_id = str(uuid.uuid4())
    decision = ResponseService.unknown_owner_followup(
        {
            "quoted_message_id": outbound_id,
            "unresolved_questions": [
                {
                    "id": str(question_id),
                    "message_id": outbound_id,
                    "awaiting_field": "owner",
                    "blocker_id": str(uuid.uuid4()),
                }
            ],
        },
        SimpleNamespace(content="I still don’t know the owner. Don’t contact anyone yet."),
        SimpleNamespace(id=employee_id),
    )
    assert decision is not None
    assert decision.messages[0].recipient_id == employee_id
    assert decision.answered_question_ids == []
    assert decision.needs_clarification is True


def test_multi_person_context_routes_to_configured_reasoning_deployment(monkeypatch):
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        AZURE_OPENAI_ENDPOINT="https://test.openai.azure.com",
        AZURE_OPENAI_API_KEY="fake",
        AZURE_OPENAI_DEPLOYMENT="small",
        AZURE_OPENAI_REASONING_DEPLOYMENT="strong",
    )
    monkeypatch.setattr("app.services.response_service.get_settings", lambda: settings)
    deployments = []
    output = ResponseDecision(
        should_respond=False,
        response_type="no_response",
        reason="Stored only",
        confidence=0.99,
        needs_clarification=False,
    )
    monkeypatch.setattr(
        "app.services.response_service.LLMService.complete",
        lambda **kwargs: deployments.append(kwargs["deployment"]) or output,
    )
    message = SimpleNamespace(
        conversation_id=uuid.uuid4(), employee_id=uuid.uuid4(), id=uuid.uuid4()
    )
    context = {
        "unresolved_questions": [],
        "issues": [],
        "mentioned_people": [{"id": "one"}, {"id": "two"}],
    }
    assert ResponseService.decide(context, message) == output
    assert deployments == ["strong"]
