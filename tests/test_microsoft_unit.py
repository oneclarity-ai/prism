import uuid

import httpx

from app.schemas.microsoft import AutomationStart
from app.services.microsoft_service import MicrosoftGraphClient, MicrosoftService, SIGNATURE


def test_initial_teams_message_uses_required_signature() -> None:
    message = MicrosoftService.initial_message_for("Asha", "Please share your update.")

    assert message.startswith("Hi Asha,")
    assert message.endswith(SIGNATURE)


def test_agent_messages_greet_people_by_first_name_only() -> None:
    message = MicrosoftService.initial_message_for("Ajay Nikumbh", "Please share your update.")

    assert message.startswith("Hi Ajay,")
    assert "Nikumbh" not in message


def test_default_initial_prompt_has_a_space_between_questions() -> None:
    assert "you? If yes" in MicrosoftService.default_initial_prompt()


def test_initial_teams_message_does_not_repeat_signature() -> None:
    message = MicrosoftService.initial_message_for("Asha", "Please share your update.\n\n" + SIGNATURE)

    assert message.count(SIGNATURE) == 1


def test_teams_message_renders_signature_as_italic_html() -> None:
    html = MicrosoftService.teams_html_message(
        "Hi Asha,\n\nPlease share your update.\n\n" + SIGNATURE
    )

    assert "<em>" in html
    assert "font-family: Georgia" in html
    assert "— " + SIGNATURE in html


def test_graph_html_message_is_saved_as_plain_text() -> None:
    content = MicrosoftService._message_content(
        {"body": {"contentType": "html", "content": "<p>Schema is ready <strong>today</strong>.</p>"}}
    )

    assert content == "Schema is ready today."


def test_targeted_automation_payload_keeps_explicit_employee_scope() -> None:
    employee_id = uuid.uuid4()
    payload = AutomationStart(target_employee_ids=[employee_id])

    assert payload.target_employee_ids == [employee_id]


def test_manager_report_uses_first_name_and_agent_signature() -> None:
    message = MicrosoftService.follow_up_message_for(
        "Sanjay Vitkare", "Quick team update: documentation is in progress."
    )

    assert message.startswith("Hi Sanjay,")
    assert "Vitkare" not in message
    assert message.endswith(SIGNATURE)


def test_graph_mail_sender_accepts_html_content(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 202

    def fake_post(*_args, **kwargs):
        captured.update(kwargs)
        return Response()

    client = object.__new__(MicrosoftGraphClient)
    monkeypatch.setattr(MicrosoftGraphClient, "_access_token", lambda _self: "test-token")
    monkeypatch.setattr(httpx, "post", fake_post)

    client.send_mail("yash@example.com", "Daily brief", "<h1>Brief</h1>", content_type="HTML")

    assert captured["json"]["message"]["body"] == {
        "contentType": "HTML", "content": "<h1>Brief</h1>"
    }
