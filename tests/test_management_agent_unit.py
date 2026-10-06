import uuid
from types import SimpleNamespace

from app.agents.management_agent import ManagementAgent, ReplyAnalysis
from app.models.employee import Employee
from app.services.response_service import ResponseService


def test_reply_analysis_rejects_unexpected_model_fields() -> None:
    try:
        ReplyAnalysis.model_validate(
            {
                "classification": "blocker",
                "completed_summary": None,
                "today_summary": None,
                "blocker_description": "Schema is missing",
                "dependency_owner_name": "Shubham",
                "eta_deadline": None,
                "missed_reason": None,
                "delivery_confirmed": False,
                "send_message_to_everyone": True,
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Structured reply analysis must reject unapproved fields")


def test_short_acknowledgements_are_not_sent_to_azure() -> None:
    from app.agents.management_agent import ManagementAgent

    assert ManagementAgent._is_non_actionable_acknowledgement("Okay 👍") is True
    assert ManagementAgent._is_non_actionable_acknowledgement("Sure, thanks") is True
    assert ManagementAgent._is_non_actionable_acknowledgement("yes, sure") is True
    assert ManagementAgent._is_non_actionable_acknowledgement("Hi sir") is True
    assert ManagementAgent._is_non_actionable_acknowledgement("hi yes") is True
    assert ManagementAgent._is_non_actionable_acknowledgement("I will send it by 4 PM") is False


def test_natural_named_help_request_is_a_blocker_signal() -> None:
    from app.services.message_intent_service import MessageIntentService

    signals = MessageIntentService.analyze(
        "I need some help of Shubham for this, as we also need the backend deployment."
    )

    assert signals.blocker is True
    assert signals.intent == "blocker"


def test_natural_named_help_request_contacts_an_owner_selected_in_the_run() -> None:
    source = Employee(id=uuid.uuid4(), name="Shivam Bhalerao", email="shivam@example.com", role="Engineer")
    owner = Employee(id=uuid.uuid4(), name="Shubham Kumar", email="shubham@example.com", role="Engineer")
    message = SimpleNamespace(content="I need some help of Shubham for the backend deployment.")
    context = {
        "message_focus": "standalone",
        "quoted_message_id": None,
        "mentioned_people": [{"id": str(owner.id), "name": owner.name, "matched_text": "Shubham"}],
        "active_automation_target_ids": [str(source.id), str(owner.id)],
    }

    decision = ResponseService.new_blocker_update(context, message, source)

    assert decision is not None
    assert decision.response_type == "dependency_followup"
    assert {item.recipient_id for item in decision.messages} == {source.id, owner.id}
    assert "I’ll check with the named owner" in decision.messages[0].text


def test_dependency_eta_request_is_short_and_natural() -> None:
    employee = Employee(name="Vaibhav Sharma", email="vaibhav@example.com", role="Engineer")

    message = ManagementAgent._natural_dependency_eta_request(
        employee,
        "Awaiting changes/inputs to the status API from Shubham sir to continue connector page updation.",
    )

    assert message == (
        "Vaibhav is waiting on the status API changes before continuing with the connector "
        "page updates. Any idea when this might be ready?"
    )


def test_owner_reference_ignores_common_honorifics() -> None:
    assert ManagementAgent._name_parts_without_honorifics("Shubham sir") == ["shubham"]
    assert ManagementAgent._name_parts_without_honorifics("Ms. Vaibhav ji") == ["vaibhav"]


def test_owner_handoff_requires_an_actual_handoff_not_a_new_work_update() -> None:
    owner = Employee(name="Raunak Patil", email="raunak@example.com", role="Engineer")

    assert ManagementAgent._is_explicit_owner_handoff("Raunak owns the dependency", owner) is True
    assert ManagementAgent._is_explicit_owner_handoff("You can follow this with Raunak", owner) is True
    assert ManagementAgent._is_explicit_owner_handoff("Raunak", owner) is True
    assert ManagementAgent._is_explicit_owner_handoff(
        "Raunak is working on a separate graph response format", owner
    ) is False
    assert ManagementAgent._is_explicit_owner_handoff("I will talk to Raunak", owner) is False


def test_dependency_request_does_not_repeat_honorifics_or_bad_grammar() -> None:
    employee = Employee(name="Shivam Kumar", email="shivam@example.com", role="Engineer")

    message = ManagementAgent._natural_dependency_eta_request(
        employee,
        "Shivam needs awaiting API to unblock progress on the shared space feature; dependency owned by Ajay sir to continue.",
    )

    assert message == (
        "Shivam is waiting for API before continuing with the shared space feature. "
        "Any idea when this might be ready?"
    )
    assert "sir" not in message.casefold()
