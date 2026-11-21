"""complete_task asks once for missing results; leftover planned cases end as skipped, not pending."""

import uuid
from pathlib import Path

from app.runtime.tools import PlatformTools
from app.worker.executor import claim_next

from .test_runs import _setup


async def test_pending_cases_block_completion_once_then_close(auth_client, tmp_path: Path):
    _, task = await _setup(auth_client, allow_bug_filing=False)
    run = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()
    await claim_next()
    org_id = (await auth_client.get("/api/v1/auth/me")).json()["org_id"]
    tools = PlatformTools(uuid.UUID(run["id"]), uuid.UUID(org_id), uuid.UUID(task["id"]), tmp_path)

    cases = await tools.save_test_plan([{"title": "A"}, {"title": "B"}, {"title": "C"}])
    await tools.record_test_result(cases[0]["id"], "pass")

    first = await tools.complete_task("done", "passed")
    assert "2 planned case(s) have no result" in first and tools.completed is None
    assert "Task marked complete" in await tools.complete_task("done", "passed")

    assert await tools.close_pending_cases("the agent finished without executing this case") == 2
    rows = (await auth_client.get(f"/api/v1/runs/{run['id']}/test-cases")).json()
    assert sorted(r["status"] for r in rows) == ["pass", "skipped", "skipped"]
    assert all(r["notes"].startswith("Not run:") for r in rows if r["status"] == "skipped")
