import uuid


async def _target(client) -> str:
    response = await client.post("/api/v1/targets", json={"name": "Shop", "base_url": "https://staging.example.com"})
    return response.json()["id"]


async def test_create_task(auth_client, qa_agent):
    target_id = await _target(auth_client)
    response = await auth_client.post(
        "/api/v1/tasks",
        json={
            "title": "Regression test checkout",
            "goal": "Find bugs in checkout before release",
            "agent_id": qa_agent["id"],
            "target_app_id": target_id,
            "scope": {"urls": ["/cart", "/checkout"], "allow_bug_filing": True},
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["status"] == "todo"
    assert task["scope"]["urls"] == ["/cart", "/checkout"]
    assert task["scope"]["allow_bug_filing"] is True
    assert task["created_by_id"] is not None


async def test_task_requires_known_agent(auth_client):
    response = await auth_client.post("/api/v1/tasks", json={"title": "x", "agent_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_filter_and_update(auth_client, qa_agent):
    for title in ("A", "B"):
        await auth_client.post("/api/v1/tasks", json={"title": title, "agent_id": qa_agent["id"]})
    tasks = (await auth_client.get("/api/v1/tasks")).json()
    assert {t["title"] for t in tasks} == {"A", "B"}

    first = tasks[0]["id"]
    updated = await auth_client.patch(f"/api/v1/tasks/{first}", json={"status": "blocked"})
    assert updated.json()["status"] == "blocked"

    blocked = (await auth_client.get("/api/v1/tasks", params={"status": "blocked"})).json()
    assert [t["id"] for t in blocked] == [first]

    bad = await auth_client.patch(f"/api/v1/tasks/{first}", json={"status": "flying"})
    assert bad.status_code == 422


async def test_requires_login(client):
    assert (await client.get("/api/v1/tasks")).status_code == 401
