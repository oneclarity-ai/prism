from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_v21 import (
    AgentFeedbackEvent,
    AgentJob,
    AgentPreference,
    AgentThread,
    AgentThreadMessage,
)
from app.services.llm_provider import FakeLLMProvider, ProviderResult
from app.services.llm_service import LLMService


class _FrozenDatetime(datetime):
    """The fixtures are dated 28-29 Oct 2026; recency checks must not depend on today's date."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def frozen_teams_clock(monkeypatch):
    for module in ("source_resolution_service", "teams_read_service"):
        monkeypatch.setattr(f"app.services.{module}.datetime", _FrozenDatetime)


class FakeReadGraph:
    def __init__(self, _db, _connection) -> None:
        pass

    def list_chats(self):
        return [
            {
                "id": "chat-allowed",
                "chatType": "group",
                "topic": "AI release",
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "meera", "displayName": "Meera"},
                ],
            }
        ]

    def list_chat_messages(self, chat_id: str, *, limit: int):
        assert chat_id == "chat-allowed"
        assert limit >= 1
        return [
            {
                "id": "message-1",
                "messageType": "message",
                "createdDateTime": "2026-10-28T09:10:00Z",
                "from": {"user": {"id": "meera", "displayName": "Meera"}},
                "body": {"contentType": "html", "content": "<p>Should QA continue?</p>"},
            }
        ]


class FakeSendGraph:
    calls: list[tuple[str, str]] = []

    def __init__(self, _db, _connection) -> None:
        pass

    def send_chat_message(self, chat_id: str, content: str):
        self.calls.append((chat_id, content))
        return {
            "id": "delivered-message-1",
            "createdDateTime": "2026-10-28T10:00:00Z",
        }


class FakeMultiSourceGraph:
    def __init__(self, _db, _connection) -> None:
        pass

    def list_chats(self):
        return [
            {
                "id": "chat-parv",
                "chatType": "oneOnOne",
                "lastUpdatedDateTime": "2026-10-29T09:00:00Z",
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "parv", "displayName": "Parv Pareek"},
                ],
            },
            {
                "id": "chat-meera",
                "chatType": "oneOnOne",
                "lastUpdatedDateTime": "2026-10-29T08:00:00Z",
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "meera", "displayName": "Meera Shah"},
                ],
            },
        ]

    def list_chat_messages(self, chat_id: str, *, limit: int):
        assert limit >= 1
        body = {
            "chat-parv": "Release is ready on Friday.",
            "chat-meera": "Release is blocked and will move to Monday.",
        }[chat_id]
        return [
            {
                "id": "same-graph-message-id",
                "messageType": "message",
                "createdDateTime": "2026-10-29T09:10:00Z",
                "from": {
                    "user": {
                        "id": chat_id.removeprefix("chat-"),
                        "displayName": "Parv Pareek" if chat_id == "chat-parv" else "Meera Shah",
                    }
                },
                "body": {"contentType": "text", "content": body},
            }
        ]


class FakeReadSourcesAndGroupDestinationGraph:
    message_calls: list[str] = []

    def __init__(self, _db, _connection) -> None:
        pass

    def list_chats(self):
        return [
            {
                "id": "chat-ajay-private",
                "chatType": "oneOnOne",
                "lastMessagePreview": {"createdDateTime": "2026-10-29T10:00:00Z"},
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "ajay", "displayName": "Ajay Nikumbh"},
                ],
            },
            {
                "id": "chat-sanjay-private",
                "chatType": "oneOnOne",
                "lastMessagePreview": {"createdDateTime": "2026-10-29T09:00:00Z"},
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "sanjay", "displayName": "Sanjay Vitkare"},
                ],
            },
            {
                "id": "chat-ajay-sanjay-group",
                "chatType": "group",
                "topic": "Ajay and Sanjay",
                "lastMessagePreview": {"createdDateTime": "2026-10-28T10:00:00Z"},
                "members": [
                    {"userId": "manager", "displayName": "Manager"},
                    {"userId": "ajay", "displayName": "Ajay Nikumbh"},
                    {"userId": "sanjay", "displayName": "Sanjay Vitkare"},
                ],
            },
        ]

    def list_chat_messages(self, chat_id: str, *, limit: int):
        self.message_calls.append(chat_id)
        assert limit >= 1
        assert chat_id in {"chat-ajay-private", "chat-sanjay-private"}
        return [
            {
                "id": f"message-{chat_id}",
                "messageType": "message",
                "createdDateTime": "2026-10-29T11:00:00Z",
                "from": {"user": {"id": chat_id, "displayName": "Teammate"}},
                "body": {"contentType": "text", "content": f"Update from {chat_id}."},
            }
        ]


def test_auto_source_resolution_persists_disclosed_job_plan(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftService.get_connection",
        lambda _db: SimpleNamespace(microsoft_user_id="manager"),
    )
    monkeypatch.setattr("app.services.teams_read_service.MicrosoftGraphClient", FakeReadGraph)
    original_source = None
    job_id = None
    try:
        client = TestClient(app)
        thread = client.get("/api/v2/agent/conversation").json()
        with SessionLocal() as db:
            stored = db.get(AgentThread, thread["id"])
            original_source = (
                stored.source_kind,
                stored.source_external_id,
                stored.source_label,
                dict(stored.source_metadata),
            )
        cleared = client.delete(f"/api/v2/agent/threads/{thread['id']}/source/teams")
        assert cleared.status_code == 200
        assert cleared.json()["source_external_id"] is None

        plan = client.post(
            "/api/v2/agent/sources/teams/resolve",
            json={"goal": "Check Meera's latest update"},
        )
        assert plan.status_code == 200
        assert plan.json()["status"] == "resolved"
        assert plan.json()["selected"]["external_id"] == "chat-allowed"
        assert plan.json()["selection_reason"] == "deterministic_alias"

        created = client.post(
            f"/api/v2/agent/threads/{thread['id']}/messages",
            json={"content": "Check Meera's latest update"},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert created.json()["source_external_id"] == "chat-allowed"
        assert created.json()["sources"][0]["selection_reason"] == "deterministic_alias"
        assert "Matched participant" in created.json()["requested_scope"]["resolution_rationale"]
        assert created.json()["requested_scope"]["limits"]["sources"] == 5
    finally:
        with SessionLocal() as db:
            if job_id:
                db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.job_id == job_id))
                db.execute(delete(AgentJob).where(AgentJob.id == job_id))
            if original_source is not None and "thread" in locals():
                stored = db.get(AgentThread, thread["id"])
                (
                    stored.source_kind,
                    stored.source_external_id,
                    stored.source_label,
                    stored.source_metadata,
                ) = original_source
            db.commit()
        get_settings.cache_clear()


def test_multisource_review_keeps_provenance_and_conflicts_visible(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftService.get_connection",
        lambda _db: SimpleNamespace(microsoft_user_id="manager"),
    )
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftGraphClient", FakeMultiSourceGraph
    )
    original_source = None
    job_id = None
    try:
        client = TestClient(app)
        thread = client.get("/api/v2/agent/conversation").json()
        with SessionLocal() as db:
            stored = db.get(AgentThread, thread["id"])
            original_source = (
                stored.source_kind,
                stored.source_external_id,
                stored.source_label,
                dict(stored.source_metadata),
            )
        client.delete(f"/api/v2/agent/threads/{thread['id']}/source/teams")
        plan = client.post(
            "/api/v2/agent/sources/teams/resolve",
            json={"goal": "What needs my attention across the team?"},
        )
        assert plan.status_code == 200
        assert [item["external_id"] for item in plan.json()["selected_sources"]] == [
            "chat-parv",
            "chat-meera",
        ]

        created = client.post(
            f"/api/v2/agent/threads/{thread['id']}/messages",
            json={"content": "What needs my attention across the team?"},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert len(created.json()["sources"]) == 2
        synced = client.post(f"/api/v2/agent/jobs/{job_id}/evidence/sync")
        assert synced.status_code == 200
        assert synced.json()["stored"] == 2
        assert {item["source_external_id"] for item in synced.json()["evidence"]} == {
            "chat-parv",
            "chat-meera",
        }
        evidence = {item["source_external_id"]: item["id"] for item in synced.json()["evidence"]}
        LLMService.provider_override = FakeLLMProvider(
            [
                ProviderResult(
                    text=(
                        '{"summary":"The release date is conflicting across chats.",'
                        f'"summary_evidence_ids":["{evidence["chat-parv"]}",'
                        f'"{evidence["chat-meera"]}"],'
                        '"attention_items":[{"title":"Conflicting release dates",'
                        '"detail":"Parv says Friday while Meera says Monday due to a blocker.",'
                        f'"evidence_ids":["{evidence["chat-parv"]}",'
                        f'"{evidence["chat-meera"]}"],"kind":"conflict",'
                        '"source_external_ids":["chat-parv","chat-meera"]}],'
                        '"manager_questions":[],"requires_reply":false,"proposed_reply":null,'
                        '"confidence":0.9,"limitations":[],"applied_preference_ids":[]}'
                    ),
                    model="fake-model",
                )
            ]
        )
        review = client.post(f"/api/v2/agent/jobs/{job_id}/review")
        assert review.status_code == 200
        assert review.json()["attention_items"][0]["kind"] == "conflict"
        assert review.json()["attention_items"][0]["source_external_ids"] == [
            "chat-parv",
            "chat-meera",
        ]
        assert review.json()["proposal"] is None
    finally:
        LLMService.provider_override = None
        with SessionLocal() as db:
            if job_id:
                db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.job_id == job_id))
                db.execute(delete(AgentJob).where(AgentJob.id == job_id))
            if original_source is not None and "thread" in locals():
                stored = db.get(AgentThread, thread["id"])
                (
                    stored.source_kind,
                    stored.source_external_id,
                    stored.source_label,
                    stored.source_metadata,
                ) = original_source
            db.commit()
        get_settings.cache_clear()


def test_multisource_draft_creates_independent_action_cards(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftService.get_connection",
        lambda _db: SimpleNamespace(microsoft_user_id="manager"),
    )
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftGraphClient", FakeMultiSourceGraph
    )
    original_source = None
    job_id = None
    try:
        client = TestClient(app)
        thread = client.get("/api/v2/agent/conversation").json()
        with SessionLocal() as db:
            stored = db.get(AgentThread, thread["id"])
            original_source = (
                stored.source_kind,
                stored.source_external_id,
                stored.source_label,
                dict(stored.source_metadata),
            )
        client.delete(f"/api/v2/agent/threads/{thread['id']}/source/teams")
        created = client.post(
            f"/api/v2/agent/threads/{thread['id']}/messages",
            json={"content": "Draft separate Teams messages to Parv and Meera."},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert len(created.json()["sources"]) == 2
        synced = client.post(f"/api/v2/agent/jobs/{job_id}/evidence/sync")
        evidence = {item["source_external_id"]: item["id"] for item in synced.json()["evidence"]}
        LLMService.provider_override = FakeLLMProvider(
            [
                ProviderResult(
                    text=(
                        '{"summary":"Both teammates need a release follow-up.",'
                        f'"summary_evidence_ids":["{evidence["chat-parv"]}",'
                        f'"{evidence["chat-meera"]}"],'
                        '"attention_items":[],"manager_questions":[],"requires_reply":true,'
                        '"proposed_reply":null,"action_plan_summary":"Confirm both release updates",'
                        '"proposed_actions":['
                        '{"destination_source_id":"chat-parv","body":"Please confirm the Friday release status.",'
                        '"reason":"Parv reported Friday.",'
                        f'"evidence_ids":["{evidence["chat-parv"]}"],"sequence":1,'
                        '"depends_on_source_ids":[]},'
                        '{"destination_source_id":"chat-meera","body":"Please confirm the blocker and Monday ETA.",'
                        '"reason":"Meera reported a blocker.",'
                        f'"evidence_ids":["{evidence["chat-meera"]}"],"sequence":2,'
                        '"depends_on_source_ids":[]}],'
                        '"confidence":0.9,"limitations":[],"applied_preference_ids":[]}'
                    ),
                    model="fake-model",
                )
            ]
        )
        review = client.post(f"/api/v2/agent/jobs/{job_id}/review")
        assert review.status_code == 200
        plan = review.json()["action_plan"]
        assert plan["summary"] == "Confirm both release updates"
        assert [item["proposal"]["destination"]["chat_id"] for item in plan["actions"]] == [
            "chat-parv",
            "chat-meera",
        ]
        first, second = [item["proposal"] for item in plan["actions"]]
        decided = client.post(
            f"/api/v2/agent/proposals/{first['id']}/decision",
            json={
                "decision": "approved",
                "expected_revision": first["revision"],
                "expected_payload_hash": first["payload_hash"],
            },
        )
        assert decided.status_code == 200
        refreshed = client.get(f"/api/v2/agent/plans/{plan['id']}").json()
        assert refreshed["actions"][0]["proposal"]["state"] == "approved"
        assert refreshed["actions"][1]["proposal"]["id"] == second["id"]
        assert refreshed["actions"][1]["proposal"]["state"] == "pending"

        bulk = client.post(
            f"/api/v2/agent/plans/{plan['id']}/approve-all",
            json={
                "items": [
                    {
                        "proposal_id": second["id"],
                        "expected_revision": second["revision"],
                        "expected_payload_hash": second["payload_hash"],
                    }
                ]
            },
        )
        assert bulk.status_code == 200
        assert all(item["proposal"]["state"] == "approved" for item in bulk.json()["actions"])
        FakeSendGraph.calls = []
        monkeypatch.setattr(
            "app.services.approved_teams_execution_service.MicrosoftService.get_connection",
            lambda _db: SimpleNamespace(microsoft_user_id="manager"),
        )
        monkeypatch.setattr(
            "app.services.approved_teams_execution_service.MicrosoftGraphClient", FakeSendGraph
        )
        assert client.post(f"/api/v2/agent/proposals/{first['id']}/execution").status_code == 201
        intermediate = client.get(f"/api/v2/agent/jobs/{job_id}").json()
        assert intermediate["state"] == "waiting_for_approval"
        assert client.post(f"/api/v2/agent/proposals/{second['id']}/execution").status_code == 201
        assert FakeSendGraph.calls == [
            ("chat-parv", "Please confirm the Friday release status."),
            ("chat-meera", "Please confirm the blocker and Monday ETA."),
        ]
        finished = client.get(f"/api/v2/agent/jobs/{job_id}/review").json()
        assert finished["action_plan"]["state"] == "completed"
        assert all(
            item["execution"]["state"] == "succeeded" for item in finished["action_plan"]["actions"]
        )
    finally:
        LLMService.provider_override = None
        with SessionLocal() as db:
            if job_id:
                db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.job_id == job_id))
                db.execute(delete(AgentJob).where(AgentJob.id == job_id))
            if original_source is not None and "thread" in locals():
                stored = db.get(AgentThread, thread["id"])
                (
                    stored.source_kind,
                    stored.source_external_id,
                    stored.source_label,
                    stored.source_metadata,
                ) = original_source
            db.commit()
        get_settings.cache_clear()


def test_group_destination_is_not_read_when_named_chats_are_the_sources(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    FakeReadSourcesAndGroupDestinationGraph.message_calls = []
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftService.get_connection",
        lambda _db: SimpleNamespace(microsoft_user_id="manager"),
    )
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftGraphClient",
        FakeReadSourcesAndGroupDestinationGraph,
    )
    original_source = None
    job_id = None
    try:
        client = TestClient(app)
        thread = client.get("/api/v2/agent/conversation").json()
        with SessionLocal() as db:
            stored = db.get(AgentThread, thread["id"])
            original_source = (
                stored.source_kind,
                stored.source_external_id,
                stored.source_label,
                dict(stored.source_metadata),
            )
        selected = client.put(
            f"/api/v2/agent/threads/{thread['id']}/source/teams",
            json={"external_id": "chat-ajay-sanjay-group"},
        )
        assert selected.status_code == 200
        prompt = (
            "Read my separate 1:1 chats with Sanjay Vitkare and Ajay Nikumbh, then draft a "
            "message to send in this group with discussion points for our evening meeting."
        )
        created = client.post(
            f"/api/v2/agent/threads/{thread['id']}/messages", json={"content": prompt}
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        sources = created.json()["sources"]
        assert [item["external_id"] for item in sources] == [
            "chat-ajay-private",
            "chat-sanjay-private",
            "chat-ajay-sanjay-group",
        ]
        assert sources[-1]["selection_reason"] == "destination"
        synced = client.post(f"/api/v2/agent/jobs/{job_id}/evidence/sync")
        assert synced.status_code == 200
        assert {item["source_external_id"] for item in synced.json()["evidence"]} == {
            "chat-ajay-private",
            "chat-sanjay-private",
        }
        assert set(FakeReadSourcesAndGroupDestinationGraph.message_calls) == {
            "chat-ajay-private",
            "chat-sanjay-private",
        }
        evidence = {item["source_external_id"]: item["id"] for item in synced.json()["evidence"]}
        LLMService.provider_override = FakeLLMProvider(
            [
                ProviderResult(
                    text=(
                        '{"summary":"Both 1:1 chats contain meeting updates.",'
                        f'"summary_evidence_ids":["{evidence["chat-ajay-private"]}",'
                        f'"{evidence["chat-sanjay-private"]}"],'
                        '"attention_items":[],"manager_questions":[],"requires_reply":true,'
                        '"proposed_reply":null,"action_plan_summary":"Evening meeting agenda",'
                        '"proposed_actions":[{"destination_source_id":"chat-ajay-sanjay-group",'
                        '"body":"For this evening, let us cover the updates and blockers from our 1:1s.",'
                        '"reason":"The manager requested a group agenda from the two 1:1 updates.",'
                        f'"evidence_ids":["{evidence["chat-ajay-private"]}",'
                        f'"{evidence["chat-sanjay-private"]}"],"sequence":1,'
                        '"depends_on_source_ids":[]}],"confidence":0.9,'
                        '"limitations":[],"applied_preference_ids":[]}'
                    ),
                    model="fake-model",
                )
            ]
        )
        review = client.post(f"/api/v2/agent/jobs/{job_id}/review")
        assert review.status_code == 200
        proposal = review.json()["action_plan"]["actions"][0]["proposal"]
        assert proposal["destination"]["chat_id"] == "chat-ajay-sanjay-group"
    finally:
        LLMService.provider_override = None
        with SessionLocal() as db:
            if job_id:
                db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.job_id == job_id))
                db.execute(delete(AgentJob).where(AgentJob.id == job_id))
            if original_source is not None and "thread" in locals():
                stored = db.get(AgentThread, thread["id"])
                (
                    stored.source_kind,
                    stored.source_external_id,
                    stored.source_label,
                    stored.source_metadata,
                ) = original_source
            db.commit()
        get_settings.cache_clear()


def test_selected_chat_is_snapshotted_and_evidence_is_deduplicated(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.teams_read_service.MicrosoftService.get_connection",
        lambda _db: SimpleNamespace(microsoft_user_id="manager"),
    )
    monkeypatch.setattr("app.services.teams_read_service.MicrosoftGraphClient", FakeReadGraph)
    thread_id = None
    original_source = None
    try:
        client = TestClient(app)
        sources = client.get("/api/v2/agent/sources/teams")
        assert sources.status_code == 200
        assert sources.json()["items"][0]["label"] == "AI release"

        thread = client.post("/api/v2/agent/threads", json={"title": "Release review"})
        assert thread.status_code == 201
        thread_id = thread.json()["id"]
        with SessionLocal() as db:
            stored_thread = db.get(AgentThread, thread_id)
            assert stored_thread is not None
            original_source = (
                stored_thread.source_kind,
                stored_thread.source_external_id,
                stored_thread.source_label,
                dict(stored_thread.source_metadata),
            )

        rejected = client.put(
            f"/api/v2/agent/threads/{thread_id}/source/teams",
            json={"external_id": "chat-substitution"},
        )
        assert rejected.status_code == 422

        selected = client.put(
            f"/api/v2/agent/threads/{thread_id}/source/teams",
            json={"external_id": "chat-allowed"},
        )
        assert selected.status_code == 200
        assert selected.json()["source_label"] == "AI release"

        preference = client.post(
            "/api/v2/agent/preferences",
            json={
                "instruction": "Keep Teams replies concise and direct.",
                "scope": "general",
                "source_thread_id": thread_id,
            },
        )
        assert preference.status_code == 201
        preference_id = preference.json()["id"]

        job = client.post(
            f"/api/v2/agent/threads/{thread_id}/messages",
            json={"content": "Draft a reply about what needs my response."},
        )
        assert job.status_code == 201
        assert job.json()["source_external_id"] == "chat-allowed"
        assert job.json()["scope_mode"] == "chat"
        assert job.json()["sources"][0]["external_id"] == "chat-allowed"

        first = client.post(f"/api/v2/agent/jobs/{job.json()['id']}/evidence/sync")
        second = client.post(f"/api/v2/agent/jobs/{job.json()['id']}/evidence/sync")
        assert first.status_code == 200
        assert first.json()["stored"] == 1
        assert first.json()["evidence"][0]["excerpt"] == "Should QA continue?"
        assert second.status_code == 200
        assert second.json()["stored"] == 0
        assert len(second.json()["evidence"]) == 1
        assert datetime.fromisoformat(second.json()["evidence"][0]["sent_at"]).astimezone(
            timezone.utc
        )

        evidence_id = second.json()["evidence"][0]["id"]
        LLMService.provider_override = FakeLLMProvider(
            [
                ProviderResult(
                    text=(
                        '{"summary":"QA is waiting for a manager decision.",'
                        '"summary_evidence_ids":["message-1"],'
                        '"attention_items":[{"title":"QA decision",'
                        '"detail":"Meera asked whether QA should continue.",'
                        '"evidence_ids":["message-1"]}],'
                        '"manager_questions":[{"question":"Should QA continue?",'
                        '"evidence_ids":["message-1"]}],'
                        '"requires_reply":true,"proposed_reply":{'
                        '"body":"Please continue testing unaffected flows.",'
                        '"reason":"Keep QA moving while the issue is clarified.",'
                        '"evidence_ids":["message-1"]},'
                        f'"confidence":0.9,"limitations":[],"applied_preference_ids":["{preference_id}"]}}'
                    ),
                    model="fake-model",
                )
            ]
        )
        review = client.post(f"/api/v2/agent/jobs/{job.json()['id']}/review")
        assert review.status_code == 200
        assert review.json()["summary"] == "QA is waiting for a manager decision."
        assert review.json()["summary_evidence_ids"] == [evidence_id]
        assert review.json()["attention_items"][0]["evidence_ids"] == [evidence_id]
        assert review.json()["manager_questions"][0]["evidence_ids"] == [evidence_id]
        assert review.json()["proposal"]["state"] == "pending"
        assert review.json()["proposal"]["evidence_ids"] == [evidence_id]
        assert review.json()["proposal"]["destination"]["chat_id"] == "chat-allowed"
        assert review.json()["proposal"]["body"] == "Please continue testing unaffected flows."
        assert review.json()["applied_preferences"] == [
            {
                "id": preference_id,
                "instruction": "Keep Teams replies concise and direct.",
                "scope": "general",
                "is_active": True,
            }
        ]

        disabled = client.put(
            f"/api/v2/agent/preferences/{preference_id}",
            json={
                "instruction": "Keep Teams replies concise and direct.",
                "scope": "general",
                "is_active": False,
            },
        )
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False

        messages = client.get(f"/api/v2/agent/threads/{thread_id}/messages")
        assert messages.status_code == 200
        job_messages = [item for item in messages.json() if item["job_id"] == job.json()["id"]]
        assert [item["role"] for item in job_messages] == ["manager", "assistant"]

        original = review.json()["proposal"]
        revised = client.post(
            f"/api/v2/agent/proposals/{original['id']}/revisions",
            json={"body": "Please continue unaffected testing and update me by 5 PM."},
        )
        assert revised.status_code == 201
        stale = client.post(
            f"/api/v2/agent/proposals/{original['id']}/decision",
            json={
                "decision": "approved",
                "expected_revision": original["revision"],
                "expected_payload_hash": original["payload_hash"],
            },
        )
        assert stale.status_code == 409
        current = revised.json()
        approved = client.post(
            f"/api/v2/agent/proposals/{current['id']}/decision",
            json={
                "decision": "approved",
                "expected_revision": current["revision"],
                "expected_payload_hash": current["payload_hash"],
            },
        )
        assert approved.status_code == 200
        restored = client.get(f"/api/v2/agent/jobs/{job.json()['id']}/review")
        assert restored.json()["proposal"]["state"] == "approved"

        FakeSendGraph.calls = []
        monkeypatch.setattr(
            "app.services.approved_teams_execution_service.MicrosoftService.get_connection",
            lambda _db: SimpleNamespace(microsoft_user_id="manager"),
        )
        monkeypatch.setattr(
            "app.services.approved_teams_execution_service.MicrosoftGraphClient", FakeSendGraph
        )
        first_send = client.post(f"/api/v2/agent/proposals/{current['id']}/execution")
        repeated_send = client.post(f"/api/v2/agent/proposals/{current['id']}/execution")
        assert first_send.status_code == 201
        assert repeated_send.status_code == 201
        assert first_send.json()["id"] == repeated_send.json()["id"]
        assert first_send.json()["state"] == "succeeded"
        assert first_send.json()["safe_result"]["external_message_id"] == "delivered-message-1"
        assert FakeSendGraph.calls == [
            ("chat-allowed", "Please continue unaffected testing and update me by 5 PM.")
        ]

        delivered = client.get(f"/api/v2/agent/jobs/{job.json()['id']}/review").json()
        assert delivered["proposal"]["state"] == "executed"
        assert delivered["execution"]["state"] == "succeeded"
        completed_job = client.get(f"/api/v2/agent/jobs/{job.json()['id']}").json()
        assert completed_job["state"] == "completed"
        timeline = client.get(f"/api/v2/agent/threads/{thread_id}/messages").json()
        assert timeline[-1]["content"] == "Delivered to AI release."
    finally:
        LLMService.provider_override = None
        with SessionLocal() as db:
            if "job" in locals() and job.status_code == 201:
                job_id = job.json()["id"]
                db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.job_id == job_id))
                db.execute(delete(AgentFeedbackEvent).where(AgentFeedbackEvent.job_id == job_id))
                db.execute(delete(AgentJob).where(AgentJob.id == job_id))
            if "preference_id" in locals():
                db.execute(
                    delete(AgentFeedbackEvent).where(
                        AgentFeedbackEvent.details["preference_id"].astext == preference_id
                    )
                )
                db.execute(delete(AgentPreference).where(AgentPreference.id == preference_id))
            if thread_id and original_source is not None:
                stored_thread = db.get(AgentThread, thread_id)
                if stored_thread is not None:
                    (
                        stored_thread.source_kind,
                        stored_thread.source_external_id,
                        stored_thread.source_label,
                        stored_thread.source_metadata,
                    ) = original_source
                db.commit()
        get_settings.cache_clear()
