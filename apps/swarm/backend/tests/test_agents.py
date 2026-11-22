async def test_create_and_list_agents(auth_client, qa_agent):
    assert qa_agent["status"] == "active"
    assert qa_agent["runtime"] == "openai_agents"
    assert qa_agent["tool_grants"] == {"file_bug": "ask_first"}

    listed = await auth_client.get("/api/v1/agents")
    assert [a["key"] for a in listed.json()] == ["qa-agent"]


async def test_duplicate_key_conflicts(auth_client, qa_agent):
    response = await auth_client.post("/api/v1/agents", json={"key": "qa-agent", "name": "Again", "role": "qa"})
    assert response.status_code == 409


async def test_invalid_key_and_grant_rejected(auth_client):
    bad_key = await auth_client.post("/api/v1/agents", json={"key": "Bad Key!", "name": "x", "role": "qa"})
    assert bad_key.status_code == 422
    bad_grant = await auth_client.post(
        "/api/v1/agents", json={"key": "ok-key", "name": "x", "role": "qa", "tool_grants": {"file_bug": "maybe"}}
    )
    assert bad_grant.status_code == 422


async def test_update_pause_resume(auth_client, qa_agent):
    agent_id = qa_agent["id"]
    updated = await auth_client.patch(
        f"/api/v1/agents/{agent_id}", json={"model": "gpt-qa", "max_turns": 40, "tool_grants": {"file_bug": "off"}}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["model"] == "gpt-qa"
    assert body["max_turns"] == 40
    assert body["tool_grants"] == {"file_bug": "off"}

    paused = await auth_client.post(f"/api/v1/agents/{agent_id}/pause")
    assert paused.json()["status"] == "paused"
    resumed = await auth_client.post(f"/api/v1/agents/{agent_id}/resume")
    assert resumed.json()["status"] == "active"


async def test_agent_cannot_report_to_itself(auth_client, qa_agent):
    response = await auth_client.patch(f"/api/v1/agents/{qa_agent['id']}", json={"reports_to_id": qa_agent["id"]})
    assert response.status_code == 409


async def test_unknown_agent_404(auth_client):
    response = await auth_client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_generate_description_needs_azure(auth_client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "azure_openai_endpoint", "")
    r = await auth_client.post(
        "/api/v1/agents/generate-description", json={"name": "Marketing agent", "role": "marketing"}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "runtime_not_ready"


async def test_generate_description_returns_draft(auth_client, monkeypatch):
    from app.api.routers import agents as router

    async def fake(name, role, department, notes):
        return f"## Mission\n{name} as {role}", 0.002

    monkeypatch.setattr(router, "job_description", fake)
    r = await auth_client.post("/api/v1/agents/generate-description", json={"name": "Ana", "role": "sales"})
    assert r.status_code == 200 and r.json()["description"].startswith("## Mission")
