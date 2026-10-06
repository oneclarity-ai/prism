from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.automation_service import DailyAutomationService


def test_daily_automation_time_check_is_deterministic() -> None:
    now = datetime(2026, 9, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    assert DailyAutomationService._is_due(now, "10:00") is True
    assert DailyAutomationService._is_due(now, "10:01") is False
    assert DailyAutomationService._is_due(now, "not-a-time") is False


def test_daily_checkins_only_run_in_a_short_schedule_window() -> None:
    on_time = datetime(2026, 9, 5, 10, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
    late = datetime(2026, 9, 5, 20, 34, tzinfo=ZoneInfo("Asia/Kolkata"))

    assert DailyAutomationService._is_within_schedule_window(on_time, "10:00") is True
    assert DailyAutomationService._is_within_schedule_window(late, "10:00") is False


def test_daily_automation_formats_deadline_in_manager_timezone() -> None:
    deadline = datetime(2026, 9, 5, 12, 30, tzinfo=ZoneInfo("UTC"))

    assert "IST" in DailyAutomationService._format_deadline(deadline)


def test_daily_digest_email_has_exactly_five_simple_sections() -> None:
    digest = """Daily manager digest

Responded: 1/1

Completed:
- Shivam: Frontend fix

Blocked:
- Shivam — Backend deployment (dependency: Shubham; severity: high)

Agent handling today:
- Shivam: recorded blocker; asked Shubham for an ETA.

Needs your attention:
- Deployment needs review
"""
    now = datetime(2026, 10, 6, 19, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    email = DailyAutomationService._daily_digest_email_html(digest, now)

    for title in [
        "Overview", "Work updates", "Blockers &amp; commitments", "Agent handling", "Manager attention",
    ]:
        assert title in email
    assert email.count("<h2") == 5
    assert "Team response: 1/1" in email
    assert "asked Shubham for an ETA" in email
