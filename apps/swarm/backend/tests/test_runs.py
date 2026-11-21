"""Run lifecycle with the fake runtime: start, live events, approvals, resume, cancel."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.db.enums import RunStatus
from app.db.models import Run
from app.db.session import SessionLocal
from app.runtime.fake import FakeAdapter
from app.runtime.registry import register_adapter
from app.worker.executor import claim_next, execute_run

GRANTS = {
    "get_task_context": "allowed",
    "get_test_login": "allowed",
    "save_test_plan": "allowed",
    "record_test_result": "allowed",
    "draft_bug": "allowed",
    "complete_task": "allowed",
    "file_bug": "ask_first",
}


@pytest.fixture(autouse=True)
def instant_fake():
    register_adapter(FakeAdapter(delay=0))
    yield
    register_adapter(FakeAdapter())


async def _setup(client, runtime="fake", allow_bug_filing=True):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"key": "qa", "name": "QA Agent", "role": "qa", "runtime": runtime, "tool_grants": GRANTS},
        )
    ).json()
    target = (
        await client.post(
            "/api/v1/targets",
            json={
                "name": "Demo",
                "base_url": "http://localhost:4000",
                "environment": "local",
                "test_login": {"username": "demo@shop.test", "password": "demo123"},
            },
        )
    ).json()
    task = (
        await client.post(
            "/api/v1/tasks",
            json={
                "title": "Regression",
                "agent_id": agent["id"],
                "target_app_id": target["id"],
                "scope": {"urls": ["/login.html"], "allow_bug_filing": allow_bug_filing},
            },
        )
    ).json()
    return agent, task


async def _work():
    run_id = await claim_next()
    assert run_id is not None
    await execute_run(run_id)
    return str(run_id)


async def test_fake_run_with_approval_and_resume(auth_client):
    agent, task = await _setup(auth_client)
    start = await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")
    assert start.status_code == 201, start.text
    run_id = start.json()["id"]

    await _work()
    run = (await auth_client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "waiting_approval"

    events = (await auth_client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert events[0]["type"] == "status"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all("demo123" not in str(e["payload"]) for e in events), "test login password leaked into events"

    cases = (await auth_client.get(f"/api/v1/runs/{run_id}/test-cases")).json()
    assert {c["status"] for c in cases} == {"pass", "fail"}

    approvals = (await auth_client.get("/api/v1/approvals", params={"status": "pending"})).json()
    assert len(approvals) == 2
    assert approvals[0]["payload"]["bug"]["title"]
    assert (await auth_client.get(f"/api/v1/tasks/{task['id']}")).json()["status"] == "blocked"

    first = await auth_client.post(f"/api/v1/approvals/{approvals[0]['id']}/decision", json={"decision": "approve"})
    assert first.json()["resume_run_id"] is None  # still one pending
    second = await auth_client.post(
        f"/api/v1/approvals/{approvals[1]['id']}/decision", json={"decision": "reject", "comment": "dupe"}
    )
    resume_id = second.json()["resume_run_id"]
    assert resume_id

    assert await _work() == resume_id
    resumed = (await auth_client.get(f"/api/v1/runs/{resume_id}")).json()
    assert resumed["status"] == "succeeded"
    assert resumed["resumes_run_id"] == run_id
    assert (await auth_client.get(f"/api/v1/runs/{run_id}")).json()["resumed_by_run_id"] == resume_id

    bugs = (await auth_client.get(f"/api/v1/runs/{resume_id}/bugs")).json()
    assert sorted(b["status"] for b in bugs) == ["approved", "rejected"]
    assert (await auth_client.get(f"/api/v1/tasks/{task['id']}")).json()["status"] == "done"


async def test_run_without_bug_filing_finishes(auth_client):
    _, task = await _setup(auth_client, allow_bug_filing=False)
    run_id = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()["id"]
    await _work()
    run = (await auth_client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "succeeded"
    assert "test cases" in run["summary"]


async def test_start_rules(auth_client):
    agent, task = await _setup(auth_client)
    await auth_client.post(f"/api/v1/agents/{agent['id']}/pause")
    assert (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).status_code == 409
    await auth_client.post(f"/api/v1/agents/{agent['id']}/resume")

    assert (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).status_code == 201
    dup = await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")
    assert dup.status_code == 409


async def test_task_run_and_approval_operations_are_idempotent(auth_client):
    _, task = await _setup(auth_client)
    body = {
        "title": "Retry-safe task",
        "agent_id": task["agent_id"],
        "operation_key": "prism:00000000-0000-0000-0000-000000000001:task",
    }
    first_task = (await auth_client.post("/api/v1/tasks", json=body)).json()
    second_task = (await auth_client.post("/api/v1/tasks", json=body)).json()
    assert second_task["id"] == first_task["id"]

    start_body = {"operation_key": "prism:00000000-0000-0000-0000-000000000001:run"}
    first = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json=start_body)).json()
    second = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json=start_body)).json()
    assert second["id"] == first["id"]
    await _work()
    approvals = (await auth_client.get("/api/v1/approvals", params={"status": "pending"})).json()
    for approval in approvals[:-1]:
        await auth_client.post(f"/api/v1/approvals/{approval['id']}/decision", json={"decision": "reject"})
    approval = approvals[-1]
    decision = {
        "decision": "approve",
        "operation_key": "prism:00000000-0000-0000-0000-000000000001:decision",
    }
    once = (await auth_client.post(f"/api/v1/approvals/{approval['id']}/decision", json=decision)).json()
    twice = (await auth_client.post(f"/api/v1/approvals/{approval['id']}/decision", json=decision)).json()
    assert twice["resume_run_id"] == once["resume_run_id"]


async def test_expired_run_leases_requeue_safe_work_and_stop_uncertain_actions(auth_client):
    from app.worker.executor import recover_stale

    _, task = await _setup(auth_client, allow_bug_filing=False)
    safe_id = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()["id"]
    assert str(await claim_next()) == safe_id
    async with SessionLocal() as session:
        await session.execute(
            update(Run)
            .where(Run.id == uuid.UUID(safe_id))
            .values(
                saved_state={"checkpoint": "safe"},
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                active_tool="browser_snapshot",
                active_tool_risky=False,
            )
        )
        await session.commit()
    await recover_stale()
    async with SessionLocal() as session:
        safe = await session.get(Run, uuid.UUID(safe_id))
        assert safe.status == RunStatus.queued and safe.saved_state == {"checkpoint": "safe"}
        safe.status = RunStatus.cancelled
        await session.commit()

    risky_task = (
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Risky", "agent_id": task["agent_id"], "scope": {}},
        )
    ).json()
    risky_id = (await auth_client.post(f"/api/v1/tasks/{risky_task['id']}/runs")).json()["id"]
    assert str(await claim_next()) == risky_id
    async with SessionLocal() as session:
        await session.execute(
            update(Run)
            .where(Run.id == uuid.UUID(risky_id))
            .values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                active_tool="browser_click",
                active_tool_risky=True,
            )
        )
        await session.commit()
    await recover_stale()
    async with SessionLocal() as session:
        risky = await session.get(Run, uuid.UUID(risky_id))
        assert risky.status == RunStatus.failed
        assert risky.error.startswith("outcome_unknown:")
    assert (await auth_client.get(f"/api/v1/tasks/{risky_task['id']}")).json()["status"] == "failed"

    legacy_task = (
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Pre-lease upgrade", "agent_id": task["agent_id"], "scope": {}},
        )
    ).json()
    legacy_id = (await auth_client.post(f"/api/v1/tasks/{legacy_task['id']}/runs")).json()["id"]
    assert str(await claim_next()) == legacy_id
    async with SessionLocal() as session:
        await session.execute(
            update(Run)
            .where(Run.id == uuid.UUID(legacy_id))
            .values(lease_owner=None, lease_token=None, lease_expires_at=None)
        )
        await session.commit()
    await recover_stale()
    async with SessionLocal() as session:
        legacy = await session.get(Run, uuid.UUID(legacy_id))
        assert legacy.status == RunStatus.failed
        assert legacy.error.startswith("outcome_unknown:")


async def test_real_runtime_needs_azure(auth_client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "azure_openai_endpoint", "")
    _, task = await _setup(auth_client, runtime="openai_agents")
    response = await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "runtime_not_ready"


async def test_cancel_queued_run(auth_client):
    _, task = await _setup(auth_client)
    run_id = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()["id"]
    cancelled = await auth_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert await claim_next() is None
    assert (await auth_client.post(f"/api/v1/runs/{run_id}/cancel")).status_code == 409


async def test_worker_heartbeat_shows_in_status(auth_client):
    from app.worker.heartbeat import beat, goodbye

    assert (await auth_client.get("/api/v1/runtime/status")).json()["workers_online"] == 0
    await beat()
    assert (await auth_client.get("/api/v1/runtime/status")).json()["workers_online"] == 1
    await goodbye()
    assert (await auth_client.get("/api/v1/runtime/status")).json()["workers_online"] == 0


async def test_analytics_and_bug_list(auth_client):
    _, task = await _setup(auth_client, allow_bug_filing=False)
    await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")
    await _work()
    data = (await auth_client.get("/api/v1/analytics", params={"days": 7})).json()
    assert data["totals"]["runs"] == 1 and data["totals"]["succeeded"] == 1
    assert len(data["by_day"]) == 7 and data["by_day"][-1]["runs"] == 1
    assert data["by_model"][0]["model"] == "scripted"
    assert data["by_agent"][0]["agent_name"] == "QA Agent"
    assert sum(b["count"] for b in data["bugs_by_severity"]) == data["totals"]["bugs"] == 2
    bugs = (await auth_client.get("/api/v1/bugs")).json()
    assert len(bugs) == 2 and bugs[0]["task_title"] == "Regression" and bugs[0]["model"] == "scripted"
    assert len((await auth_client.get("/api/v1/bugs", params={"severity": "low"})).json()) == 0


async def test_date_filters(auth_client):
    _, task = await _setup(auth_client, allow_bug_filing=False)
    await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")
    await _work()
    future = {"since": "2099-01-01T00:00:00Z"}
    assert (await auth_client.get("/api/v1/runs", params=future)).json() == []
    assert (await auth_client.get("/api/v1/bugs", params=future)).json() == []
    assert len((await auth_client.get("/api/v1/runs", params={"since": "2020-01-01T00:00:00Z"})).json()) == 1
    span = {"since": "2026-01-01T00:00:00Z", "until": "2026-01-04T00:00:00Z"}
    data = (await auth_client.get("/api/v1/analytics", params=span)).json()
    assert data["totals"]["runs"] == 0 and len(data["by_day"]) in (3, 4)  # local time zone may shift a day
