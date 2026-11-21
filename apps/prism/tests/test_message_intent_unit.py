import uuid
from types import SimpleNamespace

from app.schemas.response_decision import OutgoingDecision, ResponseDecision
from app.services.development_service import DevelopmentService
from app.services.message_intent_service import MessageIntentService
from app.services.response_service import ResponseService


def test_finished_then_testing_is_a_normal_progress_update() -> None:
    content = "I finished the deployment validation and now I’m testing rollback handling."

    signals = MessageIntentService.analyze(content)
    completed, current = MessageIntentService.split_progress(content)

    assert signals.completion is True
    assert signals.progress is True
    assert signals.blocker is False
    assert completed == "I finished the deployment validation"
    assert current == "I’m testing rollback handling"


def test_unknown_owner_and_no_blocker_are_literal_and_mutually_safe() -> None:
    unknown = MessageIntentService.analyze(
        "I’m blocked on deployment validation, and I don’t know who owns it."
    )
    clear = MessageIntentService.analyze(
        "Testing deployment validation now; there is no dependency or blocker."
    )

    assert unknown.blocker is True and unknown.owner_unknown is True
    assert clear.explicit_no_blocker is True and clear.blocker is False


def test_response_bookkeeping_is_derived_from_actual_messages() -> None:
    employee_id = uuid.uuid4()
    decision = ResponseDecision(
        should_respond=False,
        response_type="no_response",
        reason="inconsistent provider bookkeeping",
        confidence=0.9,
        needs_clarification=False,
        messages=[
            OutgoingDecision(
                recipient_id=employee_id,
                kind="conversation",
                text="I’ve noted your question.",
            )
        ],
    )

    normalized = ResponseService.normalize_response_intent(decision)

    assert normalized.should_respond is True
    assert normalized.response_type == "conversation"


def test_ordinary_question_does_not_need_an_issue_operation() -> None:
    employee = SimpleNamespace(id=uuid.uuid4())
    message = SimpleNamespace(content="Can we review the rollout plan tomorrow?")

    decision = ResponseService.ordinary_conversation_update(
        {"message_focus": "standalone", "quoted_message_id": None}, message, employee
    )

    assert decision.intent == "question"
    assert decision.issues == []
    assert decision.messages[0].kind == "conversation"


def test_dummy_journey_preview_does_not_touch_the_database(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.development_service.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )

    result = DevelopmentService.create_dummy_journey(object())

    assert result.created is True
    assert result.journey.description.startswith("DUMMY TEST")
    assert "No database" in result.message
