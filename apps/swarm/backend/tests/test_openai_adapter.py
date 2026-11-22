"""The real runtime (OpenAI Agents SDK) with a scripted model instead of Azure.

Exercises everything except the LLM itself: function tools, the Playwright MCP browser
against the Demo Shop, screenshots as artifacts, the ask-first pause, saved state and resume.
Skipped when npx (Node.js) is not installed.
"""

import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from app.core.config import get_settings
from app.runtime.openai_agents import OpenAIAgentsAdapter
from app.worker.executor import claim_next, execute_run

pytestmark = pytest.mark.skipif(shutil.which("npx") is None, reason="needs Node.js / npx for the browser tool")

SITE = Path(__file__).resolve().parents[2] / "eval-app" / "site"


@pytest.fixture
def demo_shop():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _last_output(items, name):
    """Find the output of the most recent call to tool `name` in the conversation."""
    call_ids = [
        i["call_id"]
        for i in items
        if isinstance(i, dict) and i.get("type") == "function_call" and i.get("name") == name
    ]
    for i in reversed(items):
        if isinstance(i, dict) and i.get("type") == "function_call_output" and i.get("call_id") in call_ids:
            return i["output"]
    raise AssertionError(f"no output for {name}")


class ScriptedModel(Model):
    """Plays a fixed QA session. The step is chosen from how many tool calls already happened,
    so the same script continues correctly after a pause and resume."""

    def __init__(self, base_url: str):
        self.base = base_url

    def _steps(self, items):
        return [
            ("get_task_context", {}),
            ("browser_navigate", {"url": f"{self.base}/login.html"}),
            ("browser_take_screenshot", {"filename": "login-page.png", "scale": "css"}),
            (
                "save_test_plan",
                {
                    "cases": [
                        {
                            "title": "Wrong password is rejected",
                            "given": "the demo user",
                            "when": "they log in with 'xyz'",
                            "then": "an error is shown",
                        }
                    ]
                },
            ),
            (
                "record_test_result",
                lambda: {
                    "case": "Wrong password is rejected",
                    "status": "fail",
                    "notes": "Logged in with a wrong password",
                    "screenshot": "login-page.png",
                },
            ),
            (
                "draft_bug",
                {
                    "title": "[Login] Wrong password accepted",
                    "steps": "1. Open /login.html",
                    "expected": "Error",
                    "actual": "Logged in",
                    "severity": "critical",
                    "case": None,
                },
            ),
            ("file_bug", lambda: {"bug_id": json.loads(_last_output(items, "draft_bug"))["bug_id"]}),
            ("complete_task", {"summary": "1 critical bug found and filed.", "outcome": "failed"}),
        ]

    async def get_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **_
    ):
        items = input if isinstance(input, list) else []
        done = sum(1 for i in items if isinstance(i, dict) and i.get("type") == "function_call")
        steps = self._steps(items)
        usage = Usage(requests=1, input_tokens=1000, output_tokens=100, total_tokens=1100)
        if done < len(steps):
            name, args = steps[done]
            args = args() if callable(args) else args
            call = ResponseFunctionToolCall(
                type="function_call",
                call_id=f"call_{done}",
                name=name,
                arguments=json.dumps(args),
                id=f"fc_{done}",
                status="completed",
            )
            return ModelResponse(output=[call], usage=usage, response_id=None)
        msg = ResponseOutputMessage(
            id="msg_final",
            type="message",
            role="assistant",
            status="completed",
            content=[ResponseOutputText(type="output_text", text="All done.", annotations=[])],
        )
        return ModelResponse(output=[msg], usage=usage, response_id=None)

    async def stream_response(self, *args, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError


async def test_real_runtime_with_browser_and_approval(auth_client, demo_shop, monkeypatch, tmp_path):
    settings = get_settings()
    for field, value in {
        "azure_openai_endpoint": "https://example.invalid",
        "azure_openai_api_key": "test",
        "azure_openai_api_version": "2024-10-21",
        "azure_openai_deployment": "scripted",
        "artifacts_dir": tmp_path / "artifacts",
    }.items():
        monkeypatch.setattr(settings, field, value)
    monkeypatch.setattr(OpenAIAgentsAdapter, "_model", lambda self, deployment: ScriptedModel(demo_shop))

    grants = {
        n: "allowed"
        for n in ["get_task_context", "save_test_plan", "record_test_result", "draft_bug", "complete_task", "browser"]
    }
    grants["file_bug"] = "ask_first"
    agent = (
        await auth_client.post(
            "/api/v1/agents",
            json={
                "key": "qa",
                "name": "QA",
                "role": "qa",
                "runtime": "openai_agents",
                "instructions": "Test the app.",
                "tool_grants": grants,
            },
        )
    ).json()
    target = (
        await auth_client.post("/api/v1/targets", json={"name": "Shop", "base_url": demo_shop, "environment": "local"})
    ).json()
    task = (
        await auth_client.post(
            "/api/v1/tasks",
            json={
                "title": "Login check",
                "agent_id": agent["id"],
                "target_app_id": target["id"],
                "scope": {"allow_bug_filing": True},
            },
        )
    ).json()

    run_id = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()["id"]
    await execute_run(await claim_next())

    run = (await auth_client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "waiting_approval", run
    assert run["input_tokens"] > 0 and float(run["cost_usd"]) > 0

    events = (await auth_client.get(f"/api/v1/runs/{run_id}/events")).json()
    tools_called = [e["payload"]["tool"] for e in events if e["type"] == "tool_call"]
    assert tools_called[:3] == ["get_task_context", "browser_navigate", "browser_take_screenshot"]
    nav_result = next(e for e in events if e["type"] == "tool_result" and e["payload"]["tool"] == "browser_navigate")
    assert "login.html" in nav_result["payload"]["output"]

    artifacts = (await auth_client.get(f"/api/v1/runs/{run_id}/artifacts")).json()
    assert any(a["meta"]["source"] == "login-page.png" for a in artifacts)
    image = await auth_client.get(f"/api/v1/artifacts/{artifacts[0]['id']}/file")
    assert image.status_code == 200 and image.content[:4] == b"\x89PNG"

    cases = (await auth_client.get(f"/api/v1/runs/{run_id}/test-cases")).json()
    assert cases[0]["status"] == "fail" and cases[0]["evidence_artifact_ids"]

    approval = (await auth_client.get("/api/v1/approvals", params={"status": "pending"})).json()[0]
    assert approval["action"] == "file_bug"
    assert approval["payload"]["bug"]["severity"] == "critical"
    resume_id = (
        await auth_client.post(f"/api/v1/approvals/{approval['id']}/decision", json={"decision": "approve"})
    ).json()["resume_run_id"]

    await execute_run(await claim_next())
    resumed = (await auth_client.get(f"/api/v1/runs/{resume_id}")).json()
    assert resumed["status"] == "succeeded", resumed
    assert resumed["summary"] == "1 critical bug found and filed."
    # Usage is per run: the resume run only made one model call (1000 input tokens in the script).
    assert resumed["input_tokens"] == 1000, resumed
    bugs = (await auth_client.get(f"/api/v1/runs/{resume_id}/bugs")).json()
    assert bugs[0]["status"] == "approved"
