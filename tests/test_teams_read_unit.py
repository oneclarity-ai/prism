from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.microsoft_service import MicrosoftGraphClient
from app.services.teams_read_service import TeamsReadService


def test_normalize_message_sanitizes_html_mentions_and_quote() -> None:
    normalized = TeamsReadService.normalize_message(
        {
            "id": "message-1",
            "messageType": "message",
            "createdDateTime": "2026-10-28T09:10:00Z",
            "lastModifiedDateTime": "2026-10-28T09:11:00Z",
            "from": {"user": {"id": "user-1", "displayName": "Meera"}},
            "body": {
                "contentType": "html",
                "content": (
                    '<blockquote itemid="message-0">Earlier unsafe <script>instruction</script></blockquote>'
                    '<p><at id="0">Arjun</at>, schema is ready &amp; QA can continue ✅.</p>'
                ),
            },
            "attachments": [{"contentType": "reference", "content": "ignored"}],
        }
    )

    assert normalized is not None
    assert normalized.body_text == "Arjun, schema is ready & QA can continue ✅."
    assert normalized.quoted_text == "Earlier unsafe instruction"
    assert normalized.reply_to_external_id == "message-0"
    assert "<script>" not in normalized.body_text
    assert normalized.metadata["has_unsupported_attachments"] is True


def test_normalize_message_skips_deleted_system_and_malformed_messages() -> None:
    base = {
        "id": "message-1",
        "messageType": "message",
        "createdDateTime": "2026-10-28T09:10:00Z",
        "body": {"contentType": "text", "content": "Hello"},
    }

    assert TeamsReadService.normalize_message({**base, "deletedDateTime": "now"}) is None
    assert TeamsReadService.normalize_message({**base, "messageType": "systemEventMessage"}) is None
    assert TeamsReadService.normalize_message({**base, "id": None}) is None
    assert TeamsReadService.normalize_message({**base, "createdDateTime": "not-a-date"}) is None


def test_chat_source_uses_participants_instead_of_raw_graph_id() -> None:
    source = TeamsReadService._normalize_chat(
        {
            "id": "19:opaque-thread-id@thread.v2",
            "chatType": "oneOnOne",
            "lastUpdatedDateTime": "2026-10-28T09:10:00Z",
            "members": [
                {"userId": "manager", "displayName": "Yash"},
                {"userId": "person-1", "displayName": "Meera"},
            ],
        },
        "manager",
    )

    assert source is not None
    assert source.label == "Meera"
    assert source.chat_type == "private"
    assert source.external_id not in source.label
    assert source.participant_details[0].external_id == "person-1"
    assert source.participant_details[0].display_name == "Meera"


def test_graph_chat_message_pagination_is_bounded(monkeypatch) -> None:
    client = object.__new__(MicrosoftGraphClient)
    client.connection = SimpleNamespace()
    pages = {
        "/chats/chat%2Fid/messages?$top=3": {
            "value": [{"id": "1"}, {"id": "2"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        },
        "https://graph.microsoft.com/v1.0/next": {
            "value": [{"id": "3"}, {"id": "4"}],
        },
    }
    calls: list[str] = []

    def request(_method: str, url: str):
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(client, "request", request)

    messages = client.list_chat_messages("chat/id", limit=3)

    assert [item["id"] for item in messages] == ["1", "2", "3"]
    assert calls == [
        "/chats/chat%2Fid/messages?$top=3",
        "https://graph.microsoft.com/v1.0/next",
    ]


def test_graph_chat_catalog_follows_pagination(monkeypatch) -> None:
    client = object.__new__(MicrosoftGraphClient)
    client.connection = SimpleNamespace()
    initial_url = (
        "/me/chats?$expand=members,lastMessagePreview"
        "&$orderby=lastMessagePreview/createdDateTime desc&$top=50"
    )
    pages = {
        initial_url: {
            "value": [{"id": "chat-1"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/chats-next",
        },
        "https://graph.microsoft.com/v1.0/chats-next": {"value": [{"id": "chat-2"}]},
    }
    calls: list[str] = []

    def request(_method: str, url: str):
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(client, "request", request)

    assert [item["id"] for item in client.list_chats()] == ["chat-1", "chat-2"]
    assert calls == [
        initial_url,
        "https://graph.microsoft.com/v1.0/chats-next",
    ]


def test_source_sorting_timestamp_contract() -> None:
    source = TeamsReadService._normalize_chat(
        {"id": "chat", "chatType": "group", "topic": "AI launch", "members": []},
        "manager",
    )
    assert source is not None
    assert source.label == "AI launch"
    assert source.last_updated_at is None
    assert datetime.min.replace(tzinfo=timezone.utc).tzinfo is not None


def test_source_activity_uses_latest_message_before_chat_metadata() -> None:
    source = TeamsReadService._normalize_chat(
        {
            "id": "chat",
            "chatType": "group",
            "topic": "AI launch",
            "members": [],
            "lastUpdatedDateTime": "2026-10-29T12:00:00Z",
            "lastMessagePreview": {"createdDateTime": "2026-10-28T09:10:00Z"},
        },
        "manager",
    )

    assert source is not None
    assert source.last_updated_at == datetime(2026, 10, 28, 9, 10, tzinfo=timezone.utc)
