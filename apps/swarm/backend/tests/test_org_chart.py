async def _pos(client, **body):
    r = await client.post("/api/v1/org/positions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_build_chart_and_move(auth_client, qa_agent):
    ceo = await _pos(auth_client, title="CEO", level="ceo", holder_type="human", holder_name="Ajay")
    cto = await _pos(auth_client, title="CTO", level="executive", department="Technology", parent_id=ceo["id"])
    qa = await _pos(
        auth_client,
        title="QA Agent",
        parent_id=cto["id"],
        holder_type="agent",
        agent_id=qa_agent["id"],
        holder_name="x",
    )
    assert qa["agent_id"] == qa_agent["id"]
    assert cto["holder_name"] == ""

    # Cycle: CEO cannot report to the QA agent below it.
    cyc = await auth_client.patch(f"/api/v1/org/positions/{ceo['id']}", json={"parent_id": qa["id"]})
    assert cyc.status_code == 400 and cyc.json()["error"]["code"] == "cycle"

    # Switching a seat to vacant clears the agent link.
    vac = await auth_client.patch(f"/api/v1/org/positions/{qa['id']}", json={"holder_type": "vacant"})
    assert vac.json()["agent_id"] is None

    # Deleting the CTO moves its reports up to the CEO.
    await auth_client.delete(f"/api/v1/org/positions/{cto['id']}")
    rows = {p["title"]: p for p in (await auth_client.get("/api/v1/org/positions")).json()}
    assert set(rows) == {"CEO", "QA Agent"}
    assert rows["QA Agent"]["parent_id"] == ceo["id"]


async def test_agent_roles_catalog(auth_client):
    roles = (await auth_client.get("/api/v1/agent-roles")).json()
    by_key = {r["key"]: r for r in roles}
    assert by_key["qa-agent"]["status"] == "available"
    assert by_key["sales-sdr-agent"]["status"] == "planned"


async def test_bad_level_rejected(auth_client):
    r = await auth_client.post("/api/v1/org/positions", json={"title": "X", "level": "emperor"})
    assert r.status_code == 422
