"""Parallel runs with the fake runtime: plan, capped fan-out, merge with duplicate bugs, cancel."""

import pytest

from app.runtime.fake import FakeAdapter
from app.runtime.registry import register_adapter
from app.worker.executor import claim_next, execute_run
from app.worker.orchestrator import find_duplicates, split_scope

from .test_runs import _setup

PAGES = ["/", "/login.html", "/shop.html", "/contact.html"]


@pytest.fixture(autouse=True)
def instant_fake():
    register_adapter(FakeAdapter(delay=0))
    yield
    register_adapter(FakeAdapter())


async def _task(client, pages=PAGES):
    agent, task = await _setup(client, allow_bug_filing=False)
    await client.patch(f"/api/v1/tasks/{task['id']}", json={"scope": {"urls": pages}})
    return agent, task


async def _drain():
    """Run everything that can be claimed, like the worker would, until the queue is empty."""
    while (run_id := await claim_next()) is not None:
        await execute_run(run_id)


def test_split_scope_by_pages_and_features():
    plans = split_scope({"urls": PAGES, "features": ["cart"]}, [], pages_per_agent=1, max_children=12)
    assert [p["pages"] for p in plans] == [[p] for p in PAGES]
    assert "sub-agent 2 of 4" in plans[1]["scope"]["focus"]
    assert plans[0]["scope"]["features"] == ["cart"]

    assert len(split_scope({"urls": PAGES}, [], pages_per_agent=1, max_children=2)) == 2  # groups grow
    assert [p["pages"] for p in split_scope({"urls": PAGES}, ["/a", "/b"], 1, 12)] == [["/a"], ["/b"]]
    by_feature = split_scope({"features": ["login", "search", "cart"]}, [], 2, 12)
    assert [p["scope"]["features"] for p in by_feature] == [["login", "search"], ["cart"]]
    assert len(split_scope({}, [], 1, 12)) == 1


def test_find_duplicates():
    dupes = find_duplicates(
        [
            ("a", "[Login] Wrong password is accepted"),
            ("b", "[Shop] Total is wrong for quantity 12"),
            ("c", "Login: wrong password accepted"),
            ("d", "[Auth] Successful login accepted with wrong password"),
            ("e", "[Contact] Empty message is accepted"),
            ("f", "[Shop] Empty quantity places an order"),
        ]
    )
    assert dupes == {"c": "a", "d": "a"}


async def test_parallel_run_end_to_end(auth_client):
    _, task = await _task(auth_client)
    start = await auth_client.post(
        f"/api/v1/tasks/{task['id']}/runs", json={"mode": "parallel", "max_parallel": 2, "budget_usd": 0.5}
    )
    assert start.status_code == 201, start.text
    parent = start.json()
    assert parent["kind"] == "orchestrator"

    # Plan: one sub-agent per page, parent waits.
    assert str(await claim_next()) == parent["id"]
    await execute_run(parent["id"])
    run = (await auth_client.get(f"/api/v1/runs/{parent['id']}")).json()
    assert run["status"] == "waiting_children"
    lanes = (await auth_client.get(f"/api/v1/runs/{parent['id']}/subagents")).json()
    assert [lane["pages"] for lane in lanes] == [[p] for p in PAGES]
    assert {lane["status"] for lane in lanes} == {"queued"}
    assert lanes[0]["budget_usd"] == 0.5

    # Only max_parallel sub-agents may run at once.
    first, second = await claim_next(), await claim_next()
    assert first and second
    assert await claim_next() is None
    await execute_run(first)
    await execute_run(second)
    await _drain()  # the other two sub-agents, then the merge

    run = (await auth_client.get(f"/api/v1/runs/{parent['id']}")).json()
    assert run["status"] == "succeeded", run
    assert "Final report" in run["summary"] and "duplicate" in run["summary"]
    assert run["total_tokens"] is not None and run["total_cost_usd"] is not None
    lanes = (await auth_client.get(f"/api/v1/runs/{parent['id']}/subagents")).json()
    assert {lane["status"] for lane in lanes} == {"succeeded"}
    assert all(lane["cases_total"] > 0 and lane["bugs"] == 2 for lane in lanes)

    # Results of every sub-agent are visible on the parent; the same bug from 4 agents is listed once.
    bugs = (await auth_client.get(f"/api/v1/runs/{parent['id']}/bugs")).json()
    assert len(bugs) == 8 and sum(b["duplicate_of_id"] is None for b in bugs) == 2
    assert len((await auth_client.get("/api/v1/bugs")).json()) == 2
    assert len((await auth_client.get("/api/v1/bugs", params={"include_duplicates": True})).json()) == 8
    cases = (await auth_client.get(f"/api/v1/runs/{parent['id']}/test-cases")).json()
    assert len(cases) == sum(lane["cases_total"] for lane in lanes)
    arts = (await auth_client.get(f"/api/v1/runs/{parent['id']}/artifacts")).json()
    assert any(a["kind"] == "report" for a in arts)

    events = (await auth_client.get(f"/api/v1/runs/{parent['id']}/events")).json()
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert sum(e["type"] == "subagent" for e in events) == 8  # started + finished per sub-agent
    assert (await auth_client.get(f"/api/v1/tasks/{task['id']}")).json()["status"] == "done"

    top = (await auth_client.get("/api/v1/runs", params={"top_level": True})).json()
    assert [r["id"] for r in top] == [parent["id"]]

    # Running again re-uses the same sub-tasks instead of creating new ones.
    await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json={"mode": "parallel"})
    await _drain()
    tasks = (await auth_client.get("/api/v1/tasks")).json()
    assert len(tasks) == 1 + len(PAGES)


async def test_single_run_on_chosen_pages(auth_client):
    _, task = await _task(auth_client)
    run = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json={"pages": ["/shop.html"]})).json()
    assert run["kind"] == "single" and run["options"]["pages"] == ["/shop.html"]
    await _drain()
    events = (await auth_client.get(f"/api/v1/runs/{run['id']}/events")).json()
    visited = [
        e["payload"]["arguments"]["url"]
        for e in events
        if e["type"] == "tool_call" and e["payload"]["tool"] == "browser_navigate"
    ]
    assert visited == ["http://localhost:4000/shop.html"]


async def test_cancel_parallel_run_stops_sub_agents(auth_client):
    _, task = await _task(auth_client)
    parent = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json={"mode": "parallel"})).json()
    await execute_run(await claim_next())
    running = await claim_next()  # one sub-agent is running, the others are queued

    cancelled = await auth_client.post(f"/api/v1/runs/{parent['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    lanes = (await auth_client.get(f"/api/v1/runs/{parent['id']}/subagents")).json()
    assert sorted(lane["status"] for lane in lanes) == ["cancelled", "cancelled", "cancelled", "running"]
    assert (await auth_client.get(f"/api/v1/runs/{running}")).json()["cancel_requested"] is True
    await execute_run(running)  # the worker notices the cancel flag
    assert (await auth_client.get(f"/api/v1/runs/{running}")).json()["status"] == "cancelled"
    assert (await auth_client.get(f"/api/v1/runs/{parent['id']}")).json()["status"] == "cancelled"
    assert await claim_next() is None
