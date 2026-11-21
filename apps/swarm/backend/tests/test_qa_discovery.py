"""Offline engine regression tests; all browser/model/platform boundaries are synthetic."""

import json
import uuid
from types import SimpleNamespace

import pytest
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from app.runtime.base import AgentSpec, RunContext, TaskSpec
from app.runtime.computer_mcp import OutwardGuard
from app.runtime.openai_agents import OpenAIAgentsAdapter
from app.runtime.qa_discovery import Discovery, continuation_options
from app.runtime.tools import ToolError
from openai.types.responses import ResponseFunctionToolCall


def result(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_snapshots_discover_internal_and_spa_pages_only():
    d = Discovery("https://example.invalid", ["https://example.invalid"], ["/"])
    assert d.observe(
        result(
            'Page URL: https://example.invalid/\n- link "Pricing" [ref=e1]:\n  - /url: /pricing?utm_source=x\n- link "App" [ref=e2]:\n  - /url: /#/settings\n- link "Other" [ref=e3]:\n  - /url: https://app.example.invalid/login'
        )
    )
    assert len(d.pages) == 3
    assert d.current == "https://example.invalid/"
    assert all(p["status"] != "tested" for p in d.pages.values())
    assert d.add("https://example.invalid/pricing#anchor") in d.pages
    assert d.add("https://user:password@example.invalid/private") is None
    assert d.add("javascript:alert(1)") is None


def test_crawl_traps_are_bounded_and_coverage_survives_resume():
    d = Discovery("https://example.invalid", ["https://example.invalid"], ["/"])
    for i in range(1000):
        d.add(f"/calendar?page={i}")
    assert len(d.pages) == 6 and d.truncated
    d.add("/calendar?page=0", "tested")
    resumed = Discovery(d.base, list(d.allowed), ["/"], d.view())
    assert resumed.view() == d.view()


def test_dummy_form_exception_never_approves_messages_or_new_sites():
    guard = OutwardGuard("send,submit,pay,delete", allowed_origins={"https://example.invalid"}, synthetic_forms=True)
    guard.observed(result("Page URL: https://example.invalid/\nSearch test form"))
    guard.acted("browser_fill_form", {"fields": [{"name": "search", "value": "Prism QA Test"}]})
    assert guard.reason("browser_click", {"element": "Submit", "ref": "e1"}) is None
    for label in ["Send message", "Submit payment", "Delete account", "Create account", "Publish"]:
        assert guard.reason("browser_click", {"element": label})
    assert guard.reason("browser_press_key", {"key": "Enter"})
    guard.confirmed = True
    assert guard.reason("browser_navigate", {"url": "https://sub.example.invalid"})
    guard.acted("browser_click", {})
    assert guard.reason("browser_click", {"element": "Submit"})


def test_low_risk_dummy_exception_requires_entire_synthetic_form():
    g = OutwardGuard("submit", synthetic_forms=True)
    g.observed(result("Page URL: https://example.invalid/\nSearch"))
    for fields in [
        [{"name": "email", "value": "real@customer.com"}],
        [{"name": "password", "value": "Prism QA Test"}],
        [None],
    ]:
        g.acted("browser_fill_form", {"fields": fields})
        assert g.reason("browser_click", {"element": "Submit"})


def test_ordinary_approvals_do_not_reset_budget_and_extension_is_explicit():
    opts = continuation_options({"budget_usd": 1, "max_turns": 60}, cost=0.2, turns=10)
    assert opts["budget_usd"] == pytest.approx(0.8) and opts["max_turns"] == 50
    opts = continuation_options(opts, cost=0.3, turns=20)
    assert opts["budget_usd"] == pytest.approx(0.5) and opts["max_turns"] == 30
    opts = continuation_options(opts, cost=0.1, turns=10, extension={"budget_usd": 2, "max_turns": 120})
    assert opts["budget_usd"] == pytest.approx(1.4) and opts["max_turns"] == 80
    with pytest.raises(ToolError):
        continuation_options(opts, cost=0, turns=0, extension={"budget_usd": float("nan"), "max_turns": 500})


class TestTools:
    __test__ = False

    def __init__(self):
        self.completed = None
        self.calls = 0

    def mask(self, text):
        return text

    async def collect_new_images(self):
        return []

    async def get_task_context(self):
        self.calls += 1
        return {"task": "Synthetic test"}

    async def complete_task(self, summary, outcome, rows, files):
        self.completed = {"summary": summary, "outcome": outcome}
        return "Done"


class ScriptedModel(Model):
    def __init__(self):
        self.calls = 0

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError

    async def get_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs
    ):
        self.calls += 1
        items = input if isinstance(input, list) else []
        count = sum(isinstance(i, dict) and i.get("type") == "function_call_output" for i in items)
        name = "complete_task" if count >= 5 else "get_task_context"
        args = (
            {"summary": "Synthetic pages tested.", "outcome": "passed", "results_json": None, "files": None}
            if name == "complete_task"
            else {}
        )
        call = ResponseFunctionToolCall(
            type="function_call",
            call_id=f"call_{count}",
            name=name,
            arguments=json.dumps(args),
            id=f"fc_{count}",
            status="completed",
        )
        return ModelResponse(
            output=[call], usage=Usage(requests=1, input_tokens=10, output_tokens=5, total_tokens=15), response_id=None
        )


async def test_limit_pauses_before_model_call_and_resumes_without_replaying_tools(monkeypatch, tmp_path):
    model, tools = ScriptedModel(), TestTools()

    async def emit(*args):
        pass

    async def cancelled():
        return False

    ctx = RunContext(
        str(uuid.uuid4()),
        AgentSpec("a", "prism-qa", "QA", "", "fake", {"get_task_context": "allowed", "complete_task": "allowed"}, 5, 1),
        TaskSpec(
            "t",
            "Test",
            "Test",
            {
                "discovery_mode": "automatic",
                "allowed_origins": ["https://example.invalid"],
                "request_budget_extension": True,
            },
            None,
            "https://example.invalid",
            None,
            None,
            False,
        ),
        tmp_path,
        tools,
        emit,
        cancelled,
    )
    adapter = OpenAIAgentsAdapter()
    monkeypatch.setattr(adapter, "_model", lambda _: model)
    first = await adapter.execute(ctx)
    assert first.status == "waiting_approval" and first.interruptions[0].tool == "request_budget_extension"
    assert model.calls == 2 and tools.calls == 2
    assert first.saved_state["qa_continuation"]
    ctx.saved_state = first.saved_state
    ctx.agent.max_turns = 15
    resumed = await adapter.execute(ctx)
    assert resumed.status == "succeeded"
    assert tools.calls == 5, "Completed tool actions must not replay on extension"
    assert model.calls == 6


async def _paused_run(auth_client, sessionmaker, *, action, arguments):
    import uuid
    from decimal import Decimal

    from app.db.models import Approval, Run

    agent = (
        await auth_client.post(
            "/api/v1/agents", json={"key": "auto-qa", "name": "QA Prism", "role": "qa", "runtime": "fake"}
        )
    ).json()
    task = (
        await auth_client.post(
            "/api/v1/tasks",
            json={
                "title": "Discover",
                "agent_id": agent["id"],
                "scope": {"discovery_mode": "automatic", "allowed_origins": ["https://example.invalid"]},
            },
        )
    ).json()
    run = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs", json={"max_turns": 60, "budget_usd": 1})).json()
    async with sessionmaker() as db:
        row = await db.get(Run, uuid.UUID(run["id"]))
        row.status = "waiting_approval"
        row.cost_usd = Decimal(".25")
        row.result = {"qa_turns": 20}
        row.saved_state = {"qa_continuation": [{"role": "user", "content": "Continue test"}]}
        approval = Approval(
            org_id=row.org_id,
            run_id=row.id,
            action=action,
            payload={"call_id": "call-approval", "tool": action, "arguments": arguments},
        )
        db.add(approval)
        await db.commit()
        return str(approval.id), run["id"]


async def test_budget_approval_resumes_with_only_the_approved_remainder(auth_client, sessionmaker):
    import uuid

    from app.db.models import Run

    aid, rid = await _paused_run(
        auth_client, sessionmaker, action="request_budget_extension", arguments={"budget_usd": 2, "max_turns": 120}
    )
    reply = await auth_client.post(
        f"/api/v1/approvals/{aid}/decision",
        json={
            "decision": "approve",
            "payload": {"budget_usd": "2", "max_turns": "120"},
            "operation_key": "qa-discovery-decision",
        },
    )
    assert reply.status_code == 200, reply.text
    resume_id = reply.json()["resume_run_id"]
    async with sessionmaker() as db:
        resume = await db.get(Run, uuid.UUID(resume_id))
        assert resume.options["budget_usd"] == 1.75
        assert resume.options["max_turns"] == 100
        assert resume.options["qa_budget_limit"] == 2
    repeated = await auth_client.post(
        f"/api/v1/approvals/{aid}/decision", json={"decision": "approve", "operation_key": "qa-discovery-decision"}
    )
    assert repeated.json()["resume_run_id"] == resume_id


async def test_declined_extension_stops_without_queuing_more_work(auth_client, sessionmaker):
    import uuid

    from app.db.models import Run

    aid, rid = await _paused_run(
        auth_client, sessionmaker, action="request_budget_extension", arguments={"budget_usd": 2, "max_turns": 120}
    )
    reply = await auth_client.post(f"/api/v1/approvals/{aid}/decision", json={"decision": "reject"})
    assert reply.status_code == 200 and not reply.json()["resume_run_id"]
    async with sessionmaker() as db:
        row = await db.get(Run, uuid.UUID(rid))
        assert row.status == "cancelled" and row.result["qa_turns"] == 20


async def test_site_approval_is_run_scoped_and_carries_remaining_budget(auth_client, sessionmaker):
    import uuid

    from app.db.models import Run

    aid, rid = await _paused_run(
        auth_client,
        sessionmaker,
        action="request_site_access",
        arguments={"site": "https://app.example.invalid/login", "reason": "SSO"},
    )
    reply = await auth_client.post(f"/api/v1/approvals/{aid}/decision", json={"decision": "approve"})
    assert reply.status_code == 200, reply.text
    async with sessionmaker() as db:
        row = await db.get(Run, uuid.UUID(reply.json()["resume_run_id"]))
        assert row.options["qa_approved_origins"] == ["https://app.example.invalid"]
        assert row.options["budget_usd"] == 0.75 and row.options["max_turns"] == 40


def test_hash_routes_are_not_mistaken_for_query_variants():
    d = Discovery("https://example.invalid", ["https://example.invalid"], ["/"])
    for i in range(12):
        d.add(f"/#/section-{i}")
    assert len(d.pages) == 13 and not d.truncated
    assert d.add("/?route=settings&auth_token=secret&code=one-use") == "https://example.invalid/?route=settings"
    d.observe(result("Page URL: https://example.invalid/"))
    assert d.current
    d.observe(result("Page URL: https://other.invalid/"))
    assert not d.current


async def test_declined_extension_closes_pending_cases_from_earlier_segments(auth_client, sessionmaker):
    import uuid

    from app.db.models import Run, TestCase

    aid, rid = await _paused_run(
        auth_client, sessionmaker, action="request_budget_extension", arguments={"budget_usd": 2, "max_turns": 120}
    )
    async with sessionmaker() as db:
        row = await db.get(Run, uuid.UUID(rid))
        previous = Run(
            org_id=row.org_id, task_id=row.task_id, agent_id=row.agent_id, trigger=row.trigger, status="succeeded"
        )
        db.add(previous)
        await db.flush()
        row.resumes_run_id = previous.id
        case = TestCase(run_id=previous.id, title="Unfinished authenticated route")
        db.add(case)
        await db.commit()
        case_id = case.id
    response = await auth_client.post(f"/api/v1/approvals/{aid}/decision", json={"decision": "reject"})
    assert response.status_code == 200
    async with sessionmaker() as db:
        case = await db.get(TestCase, case_id)
        assert case.status == "skipped" and "declined" in case.notes
