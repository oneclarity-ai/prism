from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_v21 import AgentJob, AgentThread, AgentThreadAlias, AgentThreadMessage


def test_agent_foundation_api_persists_a_renderable_job(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    created_thread_ids = []
    try:
        client = TestClient(app)
        before = client.get("/api/v2/agent/foundation")
        assert before.status_code == 200
        assert before.json()["enabled"] is True

        created = client.post("/api/v2/agent/foundation/demo")
        assert created.status_code == 201
        payload = created.json()
        assert payload["state"] == "queued"
        assert payload["version"] == 1
        assert payload["steps"][0]["state"] == "queued"
        assert "safe_error_detail" in payload

        with SessionLocal() as db:
            thread = db.get(AgentThread, payload["thread_id"])
            assert thread is not None
            created_thread_ids.append(thread.id)

        after = client.get("/api/v2/agent/foundation").json()
        assert after["threads"] == max(before.json()["threads"], 1)
        assert after["jobs"] == before.json()["jobs"] + 1
    finally:
        with SessionLocal() as db:
            if "payload" in locals():
                job = db.get(AgentJob, payload["id"])
                if job is not None:
                    db.delete(job)
                    db.commit()
            if created_thread_ids and before.json()["threads"] == 0:
                db.execute(delete(AgentThread).where(AgentThread.id.in_(created_thread_ids)))
                db.commit()
        get_settings.cache_clear()


def test_agent_api_is_hidden_when_feature_flag_is_off(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "false")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/v2/agent/foundation")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404


def test_agent_uses_one_canonical_conversation_and_resolves_legacy_links(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    legacy_id = uuid.uuid4()
    try:
        client = TestClient(app)
        first = client.get("/api/v2/agent/conversation")
        second = client.post("/api/v2/agent/threads", json={"title": "Must not duplicate"})
        listed = client.get("/api/v2/agent/threads")
        assert first.status_code == 200
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["is_canonical"] is True
        assert [item["id"] for item in listed.json()] == [first.json()["id"]]

        with SessionLocal() as db:
            db.add(
                AgentThreadAlias(
                    legacy_thread_id=legacy_id,
                    canonical_thread_id=uuid.UUID(first.json()["id"]),
                )
            )
            db.commit()
        resolved = client.get(f"/api/v2/agent/threads/{legacy_id}/resolve")
        assert resolved.status_code == 200
        assert resolved.json()["id"] == first.json()["id"]
    finally:
        with SessionLocal() as db:
            alias = db.get(AgentThreadAlias, legacy_id)
            if alias is not None:
                db.delete(alias)
                db.commit()
        get_settings.cache_clear()


def test_conversation_history_supports_search_and_pagination(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    get_settings.cache_clear()
    marker = f"p13-{uuid.uuid4().hex[:8]}"
    message_ids = []
    try:
        client = TestClient(app)
        thread_id = client.get("/api/v2/agent/conversation").json()["id"]
        with SessionLocal() as db:
            for index in range(5):
                message = AgentThreadMessage(
                    thread_id=uuid.UUID(thread_id),
                    role="manager",
                    content=f"{marker} item {index}" + (" 100%_done" if index == 3 else ""),
                    message_metadata={},
                )
                db.add(message)
                db.commit()  # separate transactions give each message a distinct created_at
                message_ids.append(message.id)
        base = f"/api/v2/agent/threads/{thread_id}/messages"

        everything = client.get(base, params={"q": marker}).json()
        assert [item["id"] for item in everything] == [str(i) for i in message_ids]

        newest = client.get(base, params={"q": marker, "limit": 2}).json()
        assert [item["id"] for item in newest] == [str(i) for i in message_ids[3:]]

        older = client.get(
            base, params={"q": marker, "limit": 2, "before": newest[0]["created_at"]}
        ).json()
        assert [item["id"] for item in older] == [str(i) for i in message_ids[1:3]]

        # SQL wildcards in the query are literal text.
        assert len(client.get(base, params={"q": f"{marker} item 3 100%_"}).json()) == 1
        assert client.get(base, params={"q": f"{marker}%"}).json() == []
        assert client.get(base, params={"limit": 0}).status_code == 422
    finally:
        with SessionLocal() as db:
            db.execute(delete(AgentThreadMessage).where(AgentThreadMessage.id.in_(message_ids)))
            db.commit()
        get_settings.cache_clear()
