"""The Prism operations bridge keeps engine credentials and event payloads server-side."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import operations
from app.api.routes.prism_v22 import require_v22
from app.api.routes.work import require_v24
from app.services.qa_swarm_client import QaSwarmClient


def test_workspace_data_uses_allowlist_and_hides_sensitive_fields():
    seen = []

    def engine(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/agents"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "a",
                        "name": "QA",
                        "instructions": "private",
                        "tool_grants": {"read": "allowed", "send": "ask_first", "delete": "off"},
                    }
                ],
            )
        if request.url.path.endswith("/runs"):
            return httpx.Response(200, json=[{"id": "r", "result": {"token": "private"}}])
        if request.url.path.endswith("/approvals"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "x",
                        "status": "pending",
                        "payload": {"arguments": {"site": "example.com", "password": "private"}},
                    },
                    {"id": "y", "status": "approved", "payload": None},
                ],
            )
        if request.url.path.endswith("/secrets"):
            return httpx.Response(
                200,
                json=[{"id": "s", "name": "Test login", "scope": "qa", "value": "private"}],
            )
        return httpx.Response(404)

    settings = SimpleNamespace(
        qa_swarm_configured=True,
        qa_swarm_url="http://engine.test",
        qa_swarm_email="test@example.com",
        qa_swarm_password="synthetic-password",
    )
    with QaSwarmClient(settings, transport=httpx.MockTransport(engine)) as client:
        agent = client.workspace_data("agents")[0]
        assert "instructions" not in agent
        assert "tool_grants" not in agent
        assert agent["tool_count"] == 1
        assert agent["ask_first_count"] == 1
        assert "result" not in client.workspace_data("runs")[0]
        approvals = client.workspace_data("approvals")
        approval = approvals[0]
        assert approval["payload"] == {"arguments": {"site": "example.com"}}
        assert approvals[1]["payload"] == {"arguments": {}}
        assert "value" not in client.workspace_data("secrets")[0]
        try:
            client.workspace_data("../../auth/me")
        except ValueError:
            pass
        else:
            raise AssertionError("Unknown section was accepted")
    assert len(seen) == 5


def test_run_detail_filters_tool_arguments_and_forces_artifact_download(monkeypatch):
    run_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def workspace_run_detail(self, _run_id):
            return {
                "run": {"id": str(run_id), "result": {"password": "private"}},
                "events": [
                    {
                        "seq": 1,
                        "type": "tool_call",
                        "created_at": "2026-01-01T00:00:00Z",
                        "payload": {"tool": "browser_click", "arguments": {"password": "private"}},
                    }
                ],
                "subagents": [],
                "test_cases": [],
                "bugs": [],
                "artifacts": [],
            }

        def artifact_file(self, _artifact_id):
            return b"synthetic", "text/html"

    monkeypatch.setattr(operations, "QaSwarmClient", FakeClient)
    app = FastAPI()
    app.dependency_overrides[require_v22] = lambda: None
    app.dependency_overrides[require_v24] = lambda: None
    app.include_router(operations.router)
    client = TestClient(app)

    response = client.get(f"/api/v2/operations/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["events"][0]["tool"] == "browser_click"
    assert "private" not in response.text
    assert client.get("/api/v2/operations/unknown").status_code == 404

    file_response = client.get(f"/api/v2/operations/artifacts/{artifact_id}/file")
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("application/octet-stream")
    assert file_response.headers["content-disposition"].startswith("attachment;")


def test_workspace_setup_forms_are_validated_and_do_not_launch_runs(monkeypatch):
    calls = []
    agent_id = str(uuid.uuid4())

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def workspace_save(self, section, data, record_id=None):
            calls.append((section, data, record_id))
            return {"id": str(uuid.uuid4()), "name": data.get("name", "Task")}

        def workspace_delete(self, section, record_id):
            calls.append((section, None, record_id))

        def workspace_data(self, section, **params):
            calls.append((section, params, None))
            return {"totals": {"runs": 0}}

    monkeypatch.setattr(operations, "QaSwarmClient", FakeClient)
    app = FastAPI()
    app.dependency_overrides[require_v22] = lambda: None
    app.dependency_overrides[require_v24] = lambda: None
    app.include_router(operations.router)
    client = TestClient(app)
    response = client.post(
        "/api/v2/operations/tasks", json={"title": "Prepare research", "agent_id": agent_id}
    )
    assert response.status_code == 201
    assert calls[-1][0] == "tasks"
    assert calls[-1][1]["agent_id"] == agent_id
    # Direct sends, arbitrary tool grants, and engine paths cannot be introduced by setup forms.
    assert (
        client.post(
            "/api/v2/operations/tasks",
            json={"title": "Task", "agent_id": agent_id, "start_run": True},
        ).status_code
        == 422
    )
    assert client.post("/api/v2/operations/agents", json={"tool_grants": {}}).status_code == 405
    assert (
        client.post(
            "/api/v2/operations/targets", json={"name": "Unsafe", "base_url": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    assert client.delete(f"/api/v2/operations/runs/{uuid.uuid4()}").status_code == 404
    assert client.delete("/api/v2/operations/secrets/not-a-uuid").status_code == 422
    assert client.get(f"/api/v2/operations/analytics?days=7&agent_id={agent_id}").status_code == 200
    assert calls[-1] == ("analytics", {"days": 7, "agent_id": agent_id}, None)
    assert client.get("/api/v2/operations/analytics?days=0").status_code == 422
    # The same feature gates apply to every new write endpoint.
    from app.api.routes import work

    monkeypatch.setattr(work, "get_settings", lambda: SimpleNamespace(prism_v24_enabled=False))
    del app.dependency_overrides[require_v24]
    before = len(calls)
    assert (
        client.post(
            "/api/v2/operations/tasks", json={"title": "Task", "agent_id": agent_id}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v2/operations/secrets/{uuid.uuid4()}").status_code == 404
    assert len(calls) == before


def test_workspace_secret_roundtrip_masks_response_and_preserves_value():
    seen = []

    def engine(request):
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"ok": True})
        seen.append((request.method, request.url.path, request.content))
        return httpx.Response(
            201, json={"id": "s", "name": "Synthetic", "scope": "general", "value": "secret"}
        )

    settings = SimpleNamespace(
        qa_swarm_configured=True,
        qa_swarm_url="http://engine.test",
        qa_swarm_email="test@example.com",
        qa_swarm_password="synthetic-password",
    )
    with QaSwarmClient(settings, transport=httpx.MockTransport(engine)) as client:
        result = client.workspace_save("secrets", {"name": "Synthetic", "value": "  secret  "})
        assert "value" not in result
        assert b"  secret  " in seen[-1][2]
        assert seen[-1][0:2] == ("POST", "/api/v1/secrets")
        with pytest.raises(ValueError):
            client.workspace_save("../runs", {})
        with pytest.raises(ValueError):
            client.workspace_save("secrets", {}, str(uuid.uuid4()))
        with pytest.raises(ValueError):
            client.workspace_delete("runs", str(uuid.uuid4()))
        with pytest.raises(ValueError):
            client.workspace_save("targets", {}, "../auth/me")
