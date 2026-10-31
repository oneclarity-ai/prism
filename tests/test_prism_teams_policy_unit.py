from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.agent_sources import TeamsChatSourceRead
from app.services.prism_teams_policy_service import PrismTeamsPolicyService


def _source(external_id: str) -> TeamsChatSourceRead:
    return TeamsChatSourceRead(
        external_id=external_id,
        label=external_id,
        chat_type="group",
        participants=[],
        last_updated_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
    )


def test_incremental_scan_rotates_after_the_durable_discovery_cursor(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.prism_teams_policy_service.get_settings",
        lambda: SimpleNamespace(v22_teams_poll_source_limit=2),
    )

    sources = [_source("newest"), _source("middle"), _source("oldest")]

    assert [
        item.external_id
        for item in PrismTeamsPolicyService._bounded_scan_sources(sources, "middle")
    ] == ["oldest", "newest"]


def test_normalize_teams_activity_keeps_edit_and_attachment_metadata() -> None:
    event = PrismTeamsPolicyService.normalize_event(
        {
            "id": "message-1",
            "messageType": "message",
            "createdDateTime": "2026-10-29T08:00:00Z",
            "lastModifiedDateTime": "2026-10-29T08:05:00Z",
            "body": {"contentType": "html", "content": "<p>Deployment is blocked</p>"},
            "from": {"user": {"id": "user-1", "displayName": "Asha"}},
            "attachments": [{"id": "attachment-1"}],
        }
    )

    assert event is not None
    assert event.event_kind == "updated"
    assert event.body_text == "Deployment is blocked"
    assert event.metadata["attachment_count"] == 1
    assert event.metadata["has_unsupported_attachments"] is True


def test_normalize_teams_activity_records_deletion_without_reusing_old_body() -> None:
    event = PrismTeamsPolicyService.normalize_event(
        {
            "id": "message-2",
            "messageType": "message",
            "createdDateTime": "2026-10-29T08:00:00Z",
            "deletedDateTime": "2026-10-29T08:10:00Z",
            "body": {"contentType": "html", "content": "<p>Do not retain this text</p>"},
        }
    )

    assert event is not None
    assert event.event_kind == "deleted"
    assert event.body_text == ""
    assert event.metadata["deleted_at"] == "2026-10-29T08:10:00+00:00"
