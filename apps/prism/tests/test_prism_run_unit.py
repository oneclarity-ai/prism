from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.prism_v22 import PrismTriggerPolicy
from app.services.errors import RuleViolationError
from app.services.prism_run_service import PrismRunService


def _scheduled_policy(**updates) -> PrismTriggerPolicy:
    values = {
        "prism_id": uuid.uuid4(),
        "mode": "scheduled",
        "enabled": True,
        "timezone": "Asia/Kolkata",
        "daily_time": "09:00",
        "missed_run_policy": "run_once",
        "continuous_interval_seconds": 300,
        "event_coalesce_seconds": 180,
    }
    values.update(updates)
    return PrismTriggerPolicy(**values)


def test_next_schedule_is_timezone_aware() -> None:
    policy = _scheduled_policy()
    now = datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc)  # 06:30 in Kolkata

    next_run = PrismRunService.next_scheduled_for(policy, now=now)

    assert next_run == datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)


def test_next_schedule_rolls_to_following_local_day_after_today_has_run() -> None:
    policy = _scheduled_policy()
    now = datetime(2026, 10, 30, 4, 0, tzinfo=timezone.utc)  # 09:30 in Kolkata

    next_run = PrismRunService.next_scheduled_for(policy, now=now)

    assert next_run == datetime(2026, 10, 31, 3, 30, tzinfo=timezone.utc)


def test_dst_gap_is_moved_to_a_valid_local_time() -> None:
    policy = _scheduled_policy(timezone="America/New_York", daily_time="02:30")
    now = datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc)

    next_run = PrismRunService.next_scheduled_for(policy, now=now)

    assert next_run is not None
    local = next_run.astimezone(ZoneInfo("America/New_York"))
    assert (local.hour, local.minute) >= (3, 0)


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(RuleViolationError, match="valid IANA timezone"):
        PrismRunService._validate_schedule("Mars/Olympus", "09:00")
