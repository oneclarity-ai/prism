from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.followup_intelligence_service import FollowUpIntelligenceService
from app.services.proactive_action_service import ProactiveActionService


def test_question_followup_is_fresh_text_not_a_nested_teams_message() -> None:
    question = SimpleNamespace(awaiting_field="owner")

    text = ProactiveActionService._question_followup_text(question)

    assert text == "Just checking in: who should I follow up with about this blocker?"
    assert "Sent by Yash" not in text
    assert "Hi Shivam" not in text


def test_run_window_excludes_history_before_automation_started() -> None:
    run_started = datetime.now(timezone.utc)

    assert not FollowUpIntelligenceService._is_in_run_window(
        run_started - timedelta(seconds=1), run_started
    )
    assert FollowUpIntelligenceService._is_in_run_window(run_started, run_started)
    assert FollowUpIntelligenceService._is_in_run_window(run_started + timedelta(seconds=1), run_started)
