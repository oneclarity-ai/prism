"""v2.4: any role, with its own computer. Driven through a fake engine, never a real one."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.engine.work import PrismComputer, PrismLogin
from app.models.prisms.agent_v21 import AgentThread, AgentThreadMessage
from app.models.prisms.prism_v22 import Prism
from app.models.qa.qa import QaApproval, QaRun
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.engine.work_bridge_service import verify
from app.services.prisms.prism_conversation_service import PrismConversationService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.prisms.prism_presets import grants_for, normalize_capabilities
from app.services.qa import qa_run_service
from app.services.qa.qa_swarm_client import QaSwarmClient
from tests.test_qa_tester_integration import SWARM_URL, FakeSwarm, _active_prism

TASK = "find 5 fintech companies in Bangalore and list their websites"
PASSWORD = "hunter2-very-secret"


class FakeEngine(FakeSwarm):
    """The fake testing workspace plus agents, saved logins, computers and generic results."""

    def __init__(self) -> None:
        super().__init__()
        self.agents: list[dict] = []
        self.agent_writes: list[tuple[str, dict]] = []
        self.secrets: list[dict] = []
        self.secret_values: dict[str, str] = {}
        self.computers: list[tuple[str, str]] = []
        self.screen: bytes | None = None  # the live view; None = the computer is asleep
        self.decision_payloads: list[dict | None] = []
        self.result: dict | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else {}
        method = request.method
        if path.startswith("/targets/") and method in ("GET", "PATCH"):
            target = next((t for t in self.targets if t["id"] == path.split("/")[-1]), None)
            if target is None:
                return httpx.Response(404, json={"error": {"code": "not_found"}})
            if method == "PATCH":
                target.update(body)
            return httpx.Response(200, json=target)
        if path == "/agents" and method == "GET":
            return httpx.Response(200, json=[{"id": "agent-1", "name": "QA Agent"}, *self.agents])
        if path == "/agents":
            agent = {"id": f"agent-{len(self.agents) + 2}", **body}
            self.agents.append(agent)
            self.agent_writes.append(("create", body))
            return httpx.Response(201, json=agent)
        if path.startswith("/agents/") and method == "PATCH":
            self.agent_writes.append(("update", body))
            return httpx.Response(200, json={"id": path.split("/")[-1]})
        if path == "/secrets" and method == "GET":
            scope = request.url.params.get("scope")
            return httpx.Response(200, json=[s for s in self.secrets if s["scope"] == scope])
        if path == "/secrets":
            secret = {
                "id": f"secret-{len(self.secrets) + 1}",
                "name": body["name"],
                "scope": body["scope"],
            }
            self.secrets.append(secret)
            self.secret_values[secret["id"]] = body["value"]
            return httpx.Response(201, json=secret)
        if path.startswith("/secrets/") and method == "DELETE":
            sid = path.split("/")[-1]
            self.secrets = [s for s in self.secrets if s["id"] != sid]
            self.secret_values.pop(sid, None)
            return httpx.Response(200, json={"ok": True})
        if re.fullmatch(r"/computers/[^/]+/stream", path):
            if self.screen is None:
                return httpx.Response(404, json={"error": {"code": "not_found"}})
            return httpx.Response(
                200,
                content=iter([self.screen]),
                headers={"content-type": "multipart/x-mixed-replace; boundary=frame"},
            )
        if re.fullmatch(r"/computers/[^/]+/(stop|reset)", path):
            self.computers.append((path.split("/")[2], path.split("/")[3]))
            return httpx.Response(200, json={"ok": True})
        if path.startswith("/approvals/") and path.endswith("/decision"):
            self.decision_payloads.append(body.get("payload"))
        if re.fullmatch(r"/runs/[^/]+", path) and method == "GET":
            response = super().__call__(request)
            data = response.json()
            if self.result is not None and self.status == "succeeded":
                data["result"] = self.result
            return httpx.Response(200, json=data)
        return super().__call__(request)


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("PRISM_V24_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    monkeypatch.setenv("QA_SWARM_URL", SWARM_URL)
    monkeypatch.setenv("QA_SWARM_EMAIL", "tester@example.com")
    monkeypatch.setenv("QA_SWARM_PASSWORD", "s3cret-pass")
    monkeypatch.setenv("QA_WATCHER_ENABLED", "false")
    monkeypatch.setenv("WORK_BRIDGE_SECRET", "bridge-secret-for-tests")
    get_settings.cache_clear()
    fake = FakeEngine()
    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(fake)),
    )
    yield fake
    get_settings.cache_clear()


def _work_prism(db, *, capabilities=("files", "teams"), logins="ask", description=None) -> Prism:
    prism = PrismLifecycleService.create(
        db,
        PrismCreate(
            name=f"Riya {uuid.uuid4().hex[:6]}",
            description=description or "Find B2B companies and research who to contact.",
            template_key="blank",
            capabilities=list(capabilities),
            logins_policy=logins,
        ),
    )
    from app.models.enums import PrismLifecycleState

    for target, event, confirmed in (
        (PrismLifecycleState.ONBOARDING, "onboarding_started", False),
        (PrismLifecycleState.AWAITING_CONFIRMATION, "agreement_prepared", False),
        (PrismLifecycleState.ACTIVE, "agreement_confirmed", True),
    ):
        db.refresh(prism)
        PrismLifecycleService.transition(
            db,
            prism.id,
            target=target,
            expected_lifecycle_version=prism.lifecycle_version,
            event_type=event,
            agreement_confirmed=confirmed,
        )
    db.refresh(prism)
    return prism


@pytest.fixture
def work(engine):
    with SessionLocal() as db:
        prism = _work_prism(db)
        _, thread = PrismConversationService.canonical_thread(db, prism.id)
        ids = (prism.id, thread.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(QaRun).where(QaRun.prism_id == ids[0]))
        db.execute(delete(AgentThread).where(AgentThread.prism_id == ids[0]))
        db.execute(delete(PrismLogin).where(PrismLogin.prism_id == ids[0]))
        db.execute(delete(PrismComputer).where(PrismComputer.prism_id == ids[0]))
        prism = db.get(Prism, ids[0])
        if prism is not None:
            db.delete(prism)
        db.commit()


def _plan(db, thread_id, text=TASK) -> QaRun:
    result = qa_run_service.QaRunService.handle_chat(db, thread_id=thread_id, text=text)
    assert result["handled"], result
    return db.get(QaRun, result["qa_run_id"])


def _messages(db, thread_id):
    return list(
        db.scalars(
            select(AgentThreadMessage)
            .where(AgentThreadMessage.thread_id == thread_id)
            .order_by(AgentThreadMessage.created_at)
        )
    )


def _started(db, thread_id, edits=None) -> QaRun:
    run = _plan(db, thread_id)
    return qa_run_service.QaRunService.start(db, run.id, edits or {})


# ---------- roles ----------


def test_capabilities_always_include_the_browser_and_only_known_choices() -> None:
    assert normalize_capabilities("blank", None) == ["browser"]
    assert normalize_capabilities("blank", ["files", "teams", "qa_kit", "bogus"]) == [
        "browser",
        "files",
        "teams",
    ]
    assert normalize_capabilities("executive_assistant", None) == ["browser", "teams"]
    assert "qa_kit" in normalize_capabilities("qa_tester", ["files"])


def test_grants_follow_capabilities_and_outward_tools_always_ask() -> None:
    plain = grants_for(["browser"], "never")
    assert plain["browser"] == plain["computer"] == "allowed"
    assert plain["ask_manager"] == plain["confirm_action"] == "ask_first"
    for off in ("save_file", "teams_search", "request_login", "file_bug"):
        assert off not in plain
    rich = grants_for(["browser", "files", "teams", "qa_kit"], "ask")
    assert rich["save_file"] == "allowed" and rich["teams_read_chat"] == "allowed"
    assert rich["request_login"] == "ask_first" and rich["sign_in"] == "allowed"
    assert rich["file_bug"] == "ask_first"
    assert "get_test_login" not in rich  # secure-card logins never enter the model context


def test_a_custom_role_gets_work_questions_from_its_description(engine) -> None:
    from app.services.prisms.prism_onboarding_service import PrismOnboardingService

    with SessionLocal() as db:
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(
                name=f"Sol {uuid.uuid4().hex[:6]}", description="Track competitor pricing."
            ),
        )
        try:
            keys = [q["key"] for q in PrismOnboardingService._questions_for(prism)]
            assert keys == [
                "mission",
                "work_sites",
                "work_scope",
                "work_output",
                "tone",
                "allowed_proposals",
                "restrictions",
            ]
            prism.template_key = "executive_assistant"
            assert "teams_scope" in [q["key"] for q in PrismOnboardingService._questions_for(prism)]
        finally:
            db.rollback()
            db.delete(db.get(Prism, prism.id))
            db.commit()


def test_how_ill_work_is_written_once_and_edits_are_kept(engine) -> None:
    from app.schemas.prisms.prism_v22 import PrismProfileUpdate
    from app.services.prisms.prism_profile_service import PrismProfileService

    with SessionLocal() as db:
        prism = _work_prism(db)
        try:
            content = {
                "mission": "Find leads",
                "answers": [{"question": "Which sites?", "answer": "Company websites"}],
                "restrictions": "Never message anyone",
            }
            PrismProfileService.ensure_instructions(prism, content)
            assert "Company websites" in prism.role_instructions
            assert "Never message anyone" in prism.role_instructions
            edited = PrismProfileService.update(
                db, prism.id, PrismProfileUpdate(role_instructions="You are Riya. Be brief.")
            )
            PrismProfileService.ensure_instructions(edited, content)
            assert edited.role_instructions == "You are Riya. Be brief."  # never overwritten
            updated = PrismProfileService.update(
                db, prism.id, PrismProfileUpdate(capabilities=["teams"], logins_policy="never")
            )
            assert updated.capabilities == ["browser", "teams"] and updated.logins_policy == "never"
        finally:
            db.delete(db.get(Prism, prism.id))
            db.commit()


# ---------- chat: plan card ----------


def test_a_web_task_becomes_a_plan_card_and_chat_is_left_alone(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        assert run.kind == "work" and run.state == "planned"
        plan = run.plan
        assert plan["steps"] and plan["asks_first"]
        assert "Browser" in plan["uses"] and "Files" in plan["uses"] and "Teams" in plan["uses"]
        assert plan["any_public_site"] is True  # no site named: the card says so
        assert plan["max_turns"] == 120 and plan["budget_usd"] == 2.0
        assert any(
            m.message_metadata and m.message_metadata.get("kind") == "work_plan"
            for m in _messages(db, thread_id)
        )
        for chat in ("what can you do?", "send the list to Akshay on Teams", "hi there"):
            out = qa_run_service.QaRunService.handle_chat(db, thread_id=thread_id, text=chat)
            assert out == {"handled": False}, chat


def test_a_lost_start_response_reconciles_without_duplicate_engine_work(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run = _plan(db, thread_id, TASK)
        run_id = run.id
        engine.drop_run_response_once = True
        run = qa_run_service.QaRunService.start(db, run.id)
        assert run.state == "starting" and run.swarm_run_id is None
        assert len(engine.tasks) == len(engine.started) == 1

    with SessionLocal() as db:
        qa_run_service.QaRunService.cycle(db)
        run = db.get(QaRun, run_id)
        assert run.state == "running" and run.swarm_run_id == "run-1"
        assert len(engine.tasks) == len(engine.started) == 1


def test_a_site_in_the_task_limits_where_the_browser_may_go(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run = _plan(
            db,
            thread_id,
            "check acme.com and globex.io pricing and compare with oneclarity.ai/pricing",
        )
        assert set(run.plan["sites"]) == {
            "https://acme.com",
            "https://globex.io",
            "https://oneclarity.ai",
        }
        assert run.plan["any_public_site"] is False
        started = qa_run_service.QaRunService.start(db, run.id, {})
        assert started.state == "running"
    scope = engine.tasks[0]["scope"]
    assert set(scope["allowed_origins"]) == {
        "https://acme.com",
        "https://globex.io",
        "https://oneclarity.ai",
    }


def test_edits_are_clamped_and_a_login_policy_hides_signing_in(work, engine) -> None:
    prism_id, thread_id = work
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        started = qa_run_service.QaRunService.start(
            db,
            run.id,
            {
                "max_turns": 9999,
                "budget_usd": 99,
                "steps": ["Look it up", "Report"],
                "any_public_site": True,
            },
        )
        assert started.plan["max_turns"] == get_settings().work_max_turns_cap
        assert started.plan["budget_usd"] == get_settings().work_budget_cap_usd
        assert started.plan["steps"] == ["Look it up", "Report"]
        assert any("Signing in" in a for a in started.plan["asks_first"])
        prism = db.get(Prism, prism_id)
        prism.logins_policy = "never"
        db.commit()
        from app.services.engine.work_plan_service import WorkPlanService

        assert not any("Signing in" in a for a in WorkPlanService.asks_first(prism))


def test_only_one_task_runs_at_a_time(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        _started(db, thread_id)
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="research competitors of acme.com online"
        )
        assert out == {"handled": True}
        last = _messages(db, thread_id)[-1]
        assert "still working on" in last.content and last.message_metadata["kind"] == "work_busy"
        assert len(list(db.scalars(select(QaRun).where(QaRun.thread_id == thread_id)))) == 1


# ---------- the Prism's own agent ----------


def test_the_prisms_agent_is_built_from_its_role_and_updated_only_when_it_changes(
    work, engine
) -> None:
    prism_id, thread_id = work
    with SessionLocal() as db:
        _started(db, thread_id)
    assert [kind for kind, _ in engine.agent_writes] == ["create"]
    spec = engine.agent_writes[0][1]
    assert spec["key"] == f"prism-{prism_id.hex[:8]}" and spec["role"] == "prism"
    assert spec["tool_grants"]["save_file"] == "allowed"
    assert spec["tool_grants"]["teams_search"] == "allowed"
    assert spec["tool_grants"]["request_login"] == "ask_first"
    assert spec["tool_grants"]["computer"] == "allowed"
    assert "Find B2B companies" in spec["instructions"]
    assert engine.tasks[0]["agent_id"] == "agent-2"  # its own agent, never the shared QA one
    assert "target_app_id" not in engine.tasks[0] and engine.started[0].get("pages") is None

    with SessionLocal() as db:
        run = db.scalar(select(QaRun).where(QaRun.prism_id == prism_id))
        qa_run_service.QaRunService.cancel(db, run.id)
        _started(db, thread_id)
    assert [kind for kind, _ in engine.agent_writes] == ["create"]  # unchanged role: no engine call

    from app.schemas.prisms.prism_v22 import PrismProfileUpdate
    from app.services.prisms.prism_profile_service import PrismProfileService

    with SessionLocal() as db:
        PrismProfileService.update(
            db, prism_id, PrismProfileUpdate(role_instructions="You are brief.")
        )
        run = db.scalar(select(QaRun).where(QaRun.prism_id == prism_id, QaRun.state == "running"))
        qa_run_service.QaRunService.cancel(db, run.id)
        _started(db, thread_id)
    assert [kind for kind, _ in engine.agent_writes] == ["create", "update"]
    assert "You are brief." in engine.agent_writes[1][1]["instructions"]


# ---------- watching ----------


def test_the_panel_gets_the_checklist_notes_and_a_live_frame(work, engine) -> None:
    prism_id, thread_id = work
    engine.cost = "0.0000"  # the engine only saves a run's cost when it ends
    with SessionLocal() as db:
        run = _started(db, thread_id)
        run_id = run.id
    engine.add_event(
        "tool_call", {"tool": "browser_navigate", "arguments": {"url": "https://acme.com"}}
    )
    engine.add_event(
        "checklist",
        {
            "steps": [
                {"title": "Search", "status": "done"},
                {"title": "Check size", "status": "doing"},
                {"title": "x", "status": "bogus"},
            ]
        },
    )
    engine.add_event(
        "message", {"role": "assistant", "kind": "comment", "text": "Acme is too large, skipping"}
    )
    engine.add_event(
        "artifact", {"kind": "frame", "artifact_id": "frame-secret-1", "file": "f.jpeg"}
    )
    engine.add_event(
        "artifact", {"kind": "frame", "artifact_id": "frame-secret-2", "file": "g.jpeg"}
    )
    engine.add_event("usage", {"cost_usd": 0.05, "turn": 3})
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    client = TestClient(app)
    snap = client.get(f"/api/v2/qa/runs/{run_id}").json()
    assert snap["kind"] == "work" and snap["frame"] == 2
    assert [s["status"] for s in snap["checklist"]] == [
        "done",
        "doing",
        "todo",
    ]  # unknown status is todo
    assert snap["current_url"] == "https://acme.com"
    assert any("too large" in line["text"] for line in snap["activity_log"])
    assert snap["cost_usd"] == pytest.approx(0.05)
    assert snap["plan"]["steps"] and "pages" not in snap["plan"]
    frame = client.get(f"/api/v2/qa/runs/{run_id}/frame")
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/png"
    for body in (json.dumps(snap), frame.headers.get("cache-control", "")):
        for leak in ("frame-secret", "swarm.invalid", "agent-2", "task-1", "run-1"):
            assert leak not in body


# ---------- finishing ----------


def test_a_finished_task_reports_results_files_and_downloads(work, engine) -> None:
    prism_id, thread_id = work
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    engine.status = "succeeded"
    engine.result = {
        "outcome": "passed",
        "results": [
            {"company": "Acme", "site": "acme.com", "size": "120"},
            {"company": "Globex", "site": "globex.io", "size": "80", "note": "founder-led"},
        ],
        "files": [{"name": "leads.csv", "artifact_id": "file-art-1"}],
    }
    with SessionLocal() as db:
        run = qa_run_service.QaRunService.sync(db, run_id)
        report = run.report
        assert run.state == "succeeded" and report["kind"] == "work"
        assert report["row_count"] == 2 and report["columns"] == ["company", "site", "size", "note"]
        assert report["files"] == [{"name": "leads.csv", "index": 0}]
        last = _messages(db, thread_id)[-1]
        assert last.message_metadata["kind"] == "work_report" and "2 items" in last.content
    client = TestClient(app)
    snap = client.get(f"/api/v2/qa/runs/{run_id}").json()
    assert snap["report"]["rows"][0]["company"] == "Acme" and "file-art-1" not in json.dumps(snap)
    download = client.get(f"/api/v2/qa/runs/{run_id}/files/0")
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="leads.csv"'
    assert client.get(f"/api/v2/qa/runs/{run_id}/files/3").status_code == 404

    with SessionLocal() as db:
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="what did you find in the results?"
        )
        assert out == {"handled": True}
        assert (
            "2 items" in _messages(db, thread_id)[-1].content
            or "found 2" in _messages(db, thread_id)[-1].content
        )


def test_a_failed_task_never_shows_engine_errors(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    engine.status = "failed"
    with SessionLocal() as db:
        run = qa_run_service.QaRunService.sync(db, run_id)
        assert run.state == "failed"
        text = _messages(db, thread_id)[-1].content
        assert (
            "couldn't finish" in text and "Traceback" not in text and "ExceptionGroup" not in text
        )


def test_an_uncertain_external_action_is_not_hidden_or_retried(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    engine.status = "failed"
    engine.error = "outcome_unknown: worker stopped during browser_click"
    with SessionLocal() as db:
        run = qa_run_service.QaRunService.sync(db, run_id)
        assert run.error == qa_run_service.QaRunService.OUTCOME_UNKNOWN_ERROR
        assert "check the site before trying again" in _messages(db, thread_id)[-1].content
    response = TestClient(app).get(f"/api/v2/qa/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["error"] == qa_run_service.QaRunService.OUTCOME_UNKNOWN_ERROR


# ---------- mid-task: the Prism stops and asks ----------


def _pause(engine, action: str, arguments: dict, approval_id: str) -> None:
    engine.status = "waiting_approval"
    engine.approvals.append(
        {
            "id": approval_id,
            "run_id": engine.run_id,
            "status": "pending",
            "action": action,
            "payload": {"arguments": arguments},
        }
    )


def test_an_outward_action_waits_for_a_yes_and_no_means_no(work, engine) -> None:
    _, thread_id = work
    client = TestClient(app)
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    engine.add_event("artifact", {"kind": "frame", "artifact_id": "f1", "file": "f.jpeg"})
    _pause(
        engine,
        "confirm_action",
        {
            "kind": "send",
            "site": "linkedin.com",
            "summary": "message Priya S.",
            "details": "Hi Priya, ...",
        },
        "ap-1",
    )
    with SessionLocal() as db:
        run = qa_run_service.QaRunService.sync(db, run_id)
        assert run.state == "waiting_approval"
        approval = db.scalar(select(QaApproval).where(QaApproval.qa_run_id == run_id))
        assert approval.kind == "outward_action" and approval.payload["frame"] is True
        line = _messages(db, thread_id)[-1]
        assert line.message_metadata["kind"] == "work_approval"
        assert "message Priya S." in line.content and "linkedin.com" in line.content
        approval_id = approval.id
    snap = client.get(f"/api/v2/qa/runs/{run_id}").json()
    assert snap["approvals"][0]["kind"] == "outward_action"
    assert snap["approvals"][0]["view"]["details"] == "Hi Priya, ..."
    decided = client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision", json={"decision": "reject"}
    )
    assert decided.status_code == 200
    assert engine.decisions == [("ap-1", "reject")]


def test_a_risky_click_pauses_even_when_the_agent_did_not_ask(work, engine) -> None:
    _, thread_id = work
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    engine.add_event(
        "tool_call",
        {"tool": "browser_navigate", "arguments": {"url": "https://shop.example.com/cart"}},
    )
    _pause(engine, "browser_click", {"element": "Place order", "ref": "e9"}, "ap-click")
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval = db.scalar(select(QaApproval).where(QaApproval.qa_run_id == run_id))
        assert approval.kind == "outward_action"
        assert (
            "Place order" in approval.payload["summary"]
            and "shop.example.com" in approval.payload["site"]
        )


def test_a_question_is_answered_in_chat_and_the_answer_reaches_the_run(work, engine) -> None:
    _, thread_id = work
    client = TestClient(app)
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    _pause(engine, "ask_manager", {"question": "Who are our top competitors?"}, "ap-q")
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval_id = db.scalar(select(QaApproval.id).where(QaApproval.qa_run_id == run_id))
        assert "Who are our top competitors?" in _messages(db, thread_id)[-1].content
    empty = client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision", json={"decision": "approve"}
    )
    assert empty.status_code == 422 or empty.status_code == 400 or "answer" in empty.text.lower()
    ok = client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision",
        json={"decision": "approve", "answer": "Acme and Globex"},
    )
    assert ok.status_code == 200, ok.text
    assert engine.decision_payloads[-1] == {"answer": "Acme and Globex"}
    with SessionLocal() as db:
        mine = [m for m in _messages(db, thread_id) if m.role == "manager"]
        assert mine[-1].content == "Acme and Globex"  # the answer is part of the conversation


def test_a_login_is_given_in_a_secure_card_and_the_password_goes_nowhere_else(work, engine) -> None:
    prism_id, thread_id = work
    client = TestClient(app)
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    _pause(
        engine,
        "request_login",
        {"site": "https://linkedin.com/login", "reason": "to find the head of sales"},
        "ap-l",
    )
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval_id = db.scalar(select(QaApproval.id).where(QaApproval.qa_run_id == run_id))
    missing = client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision", json={"decision": "approve"}
    )
    assert missing.status_code >= 400
    ok = client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision",
        json={
            "decision": "approve",
            "login": {"username": "yash@example.com", "password": PASSWORD, "remember": True},
        },
    )
    assert ok.status_code == 200, ok.text
    assert PASSWORD not in ok.text

    # The engine got it, encrypted there. Prism's own tables, chat and API never hold it.
    assert len(engine.secrets) == 1
    assert engine.secrets[0]["name"] == f"login:prism-{prism_id.hex[:8]}:https://linkedin.com"
    assert json.loads(engine.secret_values["secret-1"]) == {
        "username": "yash@example.com",
        "password": PASSWORD,
    }
    assert engine.decision_payloads[-1] is None  # the decision itself carries no secret
    with SessionLocal() as db:
        dump = json.dumps(
            [
                [m.content for m in _messages(db, thread_id)],
                [m.message_metadata for m in _messages(db, thread_id)],
                [a.payload for a in db.scalars(select(QaApproval))],
                [
                    [r.username_masked, r.origin, r.swarm_secret_id]
                    for r in db.scalars(select(PrismLogin))
                ],
                [r.plan for r in db.scalars(select(QaRun))],
            ],
            default=str,
        )
        assert PASSWORD not in dump and "yash@example.com" not in dump
        assert "You gave" in _messages(db, thread_id)[-1].content or any(
            "You gave" in m.content for m in _messages(db, thread_id)
        )
    for body in (
        client.get(f"/api/v2/qa/runs/{run_id}").text,
        client.get(f"/api/v2/prisms/{prism_id}/logins").text,
    ):
        assert PASSWORD not in body and "yash@example.com" not in body

    logins = client.get(f"/api/v2/prisms/{prism_id}/logins").json()
    assert [(login["site"], login["username"], login["remember"]) for login in logins] == [
        ("https://linkedin.com", "y***@example.com", True)
    ]
    removed = client.delete(f"/api/v2/prisms/{prism_id}/logins/{logins[0]['id']}")
    assert removed.status_code == 200 and removed.json() == []
    assert engine.secrets == []  # gone from the engine too


def test_a_legacy_qa_login_card_allows_only_its_approved_redirect_origin(work, engine) -> None:
    prism_id, thread_id = work
    with SessionLocal() as db:
        prism = db.get(Prism, prism_id)
        prism.template_key = "qa_tester"
        prism.capabilities = ["browser", "files", "qa_kit"]
        prism.logins_policy = "ask"
        db.commit()
        run = _plan(db, thread_id, "test https://beta.example.com/login")
        assert run.kind == "qa"
        legacy = dict(run.plan)
        legacy.pop("discovery_mode")
        run.plan = legacy
        db.commit()
        run = qa_run_service.QaRunService.start(db, run.id)
        assert engine.targets[0]["extra_origins"] == []
        run_id = run.id

    _pause(
        engine,
        "request_login",
        {"site": "https://example.com/login", "reason": "sign in"},
        "ap-redirect",
    )
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval_id = db.scalar(select(QaApproval.id).where(QaApproval.qa_run_id == run_id))

    response = TestClient(app).post(
        f"/api/v2/qa/approvals/{approval_id}/decision",
        json={
            "decision": "approve",
            "login": {"username": "tester@example.com", "password": PASSWORD, "remember": True},
        },
    )
    assert response.status_code == 200
    assert engine.targets[0]["extra_origins"] == ["https://example.com"]
    assert engine.decision_payloads[-1] is None
    assert PASSWORD not in response.text

    with QaSwarmClient(get_settings(), transport=httpx.MockTransport(engine)) as client:
        client.allow_target_origin(engine.targets[0]["id"], "https://example.com")
    assert engine.targets[0]["extra_origins"] == ["https://example.com"]


def test_automatic_qa_login_cannot_silently_expand_to_another_site(work, engine) -> None:
    prism_id, thread_id = work
    with SessionLocal() as db:
        prism = db.get(Prism, prism_id)
        prism.template_key = "qa_tester"
        prism.capabilities = ["browser", "qa_kit"]
        db.commit()
        run = _plan(db, thread_id, "test https://beta.example.com")
        qa_run_service.QaRunService.start(db, run.id)
        run_id = run.id
    _pause(
        engine, "request_login", {"site": "https://example.com/login", "reason": "SSO"}, "ap-login"
    )
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval_id = db.scalar(select(QaApproval.id).where(QaApproval.qa_run_id == run_id))
    response = TestClient(app).post(
        f"/api/v2/qa/approvals/{approval_id}/decision",
        json={
            "decision": "approve",
            "login": {"username": "tester@example.com", "password": PASSWORD},
        },
    )
    assert response.status_code == 422 and "Approve access" in response.text
    assert engine.secrets == [] and engine.targets[0]["extra_origins"] == []


def test_a_login_for_one_task_is_removed_when_the_task_ends(work, engine) -> None:
    prism_id, thread_id = work
    client = TestClient(app)
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    _pause(engine, "request_login", {"site": "https://acme.com", "reason": ""}, "ap-once")
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
        approval_id = db.scalar(select(QaApproval.id).where(QaApproval.qa_run_id == run_id))
    client.post(
        f"/api/v2/qa/approvals/{approval_id}/decision",
        json={
            "decision": "approve",
            "login": {"username": "bob", "password": PASSWORD, "remember": False},
        },
    )
    assert len(engine.secrets) == 1
    engine.status = "succeeded"
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    assert engine.secrets == []
    assert client.get(f"/api/v2/prisms/{prism_id}/logins").json() == []


# ---------- the computer panel ----------


def test_the_computer_is_asleep_working_or_waiting_and_resets_cleanly(work, engine) -> None:
    prism_id, thread_id = work
    client = TestClient(app)
    assert client.get(f"/api/v2/prisms/{prism_id}/computer").json()["state"] == "asleep"
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
    state = client.get(f"/api/v2/prisms/{prism_id}/computer").json()
    assert state["state"] == "working" and state["run_id"] == str(run_id)
    assert client.post(f"/api/v2/prisms/{prism_id}/computer/reset").status_code >= 400  # mid-task
    _pause(engine, "ask_manager", {"question": "?"}, "ap-w")
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    assert client.get(f"/api/v2/prisms/{prism_id}/computer").json()["state"] == "waiting"

    with SessionLocal() as db:
        qa_run_service.QaRunService.cancel(db, run_id)
    engine.secrets.append(
        {"id": "s9", "name": "login:x", "scope": f"prism:prism-{prism_id.hex[:8]}"}
    )
    reset = client.post(f"/api/v2/prisms/{prism_id}/computer/reset")
    assert reset.status_code == 200 and reset.json()["state"] == "asleep"
    assert (f"prism-{prism_id.hex[:8]}", "reset") in engine.computers and engine.secrets == []


def test_an_offline_engine_reads_as_my_computer_is_offline(work, engine, monkeypatch) -> None:
    prism_id, _ = work

    def offline():
        raise qa_run_service.SwarmError("My testing workspace is offline right now.")

    monkeypatch.setattr(qa_run_service, "make_client", offline)
    state = TestClient(app).get(f"/api/v2/prisms/{prism_id}/computer").json()
    assert state["state"] == "unavailable" and "offline" in state["reason"]


def test_the_flag_hides_everything_and_qa_stays_as_it_was(engine, monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V24_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(app)
    with SessionLocal() as db:
        prism = _work_prism(db)
        _, thread = PrismConversationService.canonical_thread(db, prism.id)
        try:
            assert client.get(f"/api/v2/prisms/{prism.id}/computer").status_code == 404
            assert client.get("/api/v2/qa/status").json()["computers"] is False
            out = qa_run_service.QaRunService.handle_chat(db, thread_id=thread.id, text=TASK)
            assert out == {"handled": False}  # a plain Prism has no computer without v2.4
        finally:
            db.execute(delete(AgentThread).where(AgentThread.prism_id == prism.id))
            db.delete(db.get(Prism, prism.id))
            db.commit()


def test_a_qa_tester_runs_on_its_own_agent_when_computers_are_on(engine) -> None:
    with SessionLocal() as db:
        prism = _active_prism(db)
        _, thread = PrismConversationService.canonical_thread(db, prism.id)
        try:
            assert prism.capabilities == ["browser", "files", "qa_kit"]
            result = qa_run_service.QaRunService.handle_chat(
                db, thread_id=thread.id, text="test oneclarity.ai, check pricing"
            )
            run = qa_run_service.QaRunService.start(db, result["qa_run_id"], {})
            assert run.kind == "qa" and run.state == "running"
            grants = engine.agent_writes[0][1]["tool_grants"]
            assert grants["save_test_plan"] == "allowed" and grants["file_bug"] == "ask_first"
            assert "QA tester" in engine.agent_writes[0][1]["instructions"]
            assert engine.targets and engine.targets[0]["base_url"].startswith(
                "https://oneclarity.ai"
            )
            qa_run_service.QaRunService.cancel(db, run.id)
        finally:
            db.execute(delete(QaRun).where(QaRun.prism_id == prism.id))
            db.execute(delete(AgentThread).where(AgentThread.prism_id == prism.id))
            db.execute(delete(PrismComputer).where(PrismComputer.prism_id == prism.id))
            db.delete(db.get(Prism, prism.id))
            db.commit()


# ---------- Teams for the computer, through the signed bridge ----------


def _sign(body: bytes, *, secret="bridge-secret-for-tests", stamp=None) -> dict:
    stamp = str(stamp if stamp is not None else int(time.time()))
    sig = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "X-Prism-Timestamp": stamp,
        "X-Prism-Signature": sig,
        "Content-Type": "application/json",
    }


def test_the_bridge_only_accepts_the_engine(engine) -> None:
    body = b"{}"
    secret = "bridge-secret-for-tests"
    stamp = str(int(time.time()))
    good = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    assert verify(secret, stamp, body, good)
    assert not verify(secret, stamp, body, good[:-1] + "0")
    assert not verify(secret, stamp, b"{ }", good)  # changed body
    assert not verify(secret, str(int(time.time()) - 3600), body, good)  # stale
    assert not verify(None, stamp, body, good)  # no secret configured: nothing is accepted
    client = TestClient(app)
    assert client.post("/api/v2/bridge/runs/run-1/teams/read", content=body).status_code == 401
    forged = client.post(
        "/api/v2/bridge/runs/run-1/teams/read", content=body, headers=_sign(body, secret="wrong")
    )
    assert forged.status_code == 401


def test_teams_tools_need_the_capability_and_drafts_become_cards(work, engine, monkeypatch) -> None:
    from app.models.people.employee import Employee
    from app.schemas.prisms.agent_sources import TeamsChatSourceRead
    from app.services.teams.teams_read_service import TeamsReadService

    prism_id, thread_id = work
    client = TestClient(app)
    tag = uuid.uuid4().hex[:6]
    monkeypatch.setattr(
        TeamsReadService,
        "list_sources",
        staticmethod(
            lambda db: [
                TeamsChatSourceRead(
                    external_id=f"chat-{tag}",
                    label=f"Akshay{tag} Aher",
                    chat_type="private",
                    participants=[f"Akshay{tag} Aher"],
                )
            ]
        ),
    )
    with SessionLocal() as db:
        run_id = _started(db, thread_id).id
        db.add(
            Employee(name=f"Akshay{tag} Aher", email=f"akshay{tag}@example.com", role="Team member")
        )
        db.commit()
    body = json.dumps({"to": f"akshay{tag}", "body": "Here is the list of leads."}).encode()
    drafted = client.post(
        "/api/v2/bridge/runs/run-1/teams/draft", content=body, headers=_sign(body)
    )
    assert drafted.status_code == 200, drafted.text
    assert "Nothing was sent" in drafted.json()["result"]
    with SessionLocal() as db:
        from app.models.prisms.agent_v21 import ActionProposal, AgentJob

        job = db.scalar(select(AgentJob).where(AgentJob.thread_id == thread_id))
        assert job is not None and job.state.value == "waiting_for_approval"
        proposal = db.scalar(select(ActionProposal).where(ActionProposal.job_id == job.id))
        assert proposal.body == "Here is the list of leads."  # waits for the manager's own approval
        assert _messages(db, thread_id)[-1].message_metadata["kind"] == "conversation_review"
        assert not any(
            m.role == "manager" and "Draft a message" in m.content for m in _messages(db, thread_id)
        )

        # Without the Teams capability the same call is refused in plain words.
        prism = db.get(Prism, prism_id)
        prism.capabilities = ["browser"]
        db.commit()
    refused = client.post(
        "/api/v2/bridge/runs/run-1/teams/draft", content=body, headers=_sign(body)
    )
    assert refused.status_code >= 400 and "Teams" in refused.text
    other = client.post(
        "/api/v2/bridge/runs/unknown-run/teams/draft", content=body, headers=_sign(body)
    )
    assert other.status_code == 404
    with SessionLocal() as db:
        db.execute(delete(Employee).where(Employee.email == f"akshay{tag}@example.com"))
        db.commit()
    del run_id


def test_computer_task_spend_is_its_own_category_in_the_dashboard(work, engine) -> None:
    from app.models.llm.llm_usage import LLMUsage
    from app.services.qa.qa_spend_service import FEATURE_WORK, QaSpendService

    _, thread_id = work
    tag = uuid.uuid4().hex[:8]
    engine.run_id = f"run-{tag}"
    with SessionLocal() as db:
        _started(db, thread_id)
    engine.run_list = [
        {
            "id": f"run-{tag}",
            "status": "succeeded",
            "cost_usd": "0.0400",
            "input_tokens": 900,
            "output_tokens": 40,
            "model": "gpt-5-mini",
            "started_at": "2026-11-02T10:00:00+00:00",
            "ended_at": "2026-11-02T10:02:00+00:00",
        }
    ]
    key = f"qa-run:run-{tag}"
    try:
        with SessionLocal() as db, qa_run_service.make_client() as client:
            assert QaSpendService.sync(db, client) == 1
            row = db.scalar(select(LLMUsage).where(LLMUsage.request_id == key))
            assert row.feature == FEATURE_WORK == "prism_computer_tasks"
    finally:
        with SessionLocal() as db:
            db.execute(delete(LLMUsage).where(LLMUsage.request_id == key))
            db.commit()


def test_the_live_screen_streams_while_the_computer_runs_and_is_a_clean_404_when_asleep(
    work, engine
) -> None:
    prism_id, _ = work
    client = TestClient(app)
    asleep = client.get(f"/api/v2/prisms/{prism_id}/computer/live")
    assert asleep.status_code == 404
    assert "asleep" in asleep.text and "swarm" not in asleep.text.lower()

    frame = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 4\r\n\r\n\xff\xd8\xff\xd9\r\n"
    engine.screen = frame * 2
    live = client.get(f"/api/v2/prisms/{prism_id}/computer/live")
    assert live.status_code == 200
    assert live.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert live.content == frame * 2


def test_a_draft_about_my_findings_to_a_colleague_on_teams_uses_the_findings(
    work, engine, monkeypatch
) -> None:
    """ "...the companies you found... send to Sanjay on Teams" is my work going out, not a Teams read."""

    from app.models.prisms.agent_v21 import ActionProposal, AgentJob
    from app.schemas.prisms.agent_sources import TeamsChatSourceRead
    from app.services.llm import llm_service
    from app.services.prisms.prism_teams_policy_service import PrismTeamsPolicyService

    prism_id, thread_id = work
    tag = uuid.uuid4().hex[:6]
    chat = TeamsChatSourceRead(
        external_id=f"dm-{tag}",
        label=f"Sanjay{tag} K",
        chat_type="private",
        participants=[f"Sanjay{tag} K"],
    )
    monkeypatch.setattr(
        PrismTeamsPolicyService,
        "allowed_sources",
        staticmethod(lambda db, prism_id: (None, [chat])),
    )
    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return qa_run_service._Answer(
            reply="Here's a draft for Sanjay.",
            draft_to=f"Sanjay{tag}",
            draft_body="Hi Sanjay, I'm Yash's research assistant.\n- Miro: miro.com",
        )

    monkeypatch.setattr(llm_service.LLMService, "complete", staticmethod(fake))
    with SessionLocal() as db:
        db.add(
            QaRun(
                prism_id=prism_id,
                thread_id=thread_id,
                kind="work",
                state="succeeded",
                plan={"title": "Find companies"},
                report={"summary": "Found 1", "rows": [{"Company": "Miro", "Website": "miro.com"}]},
            )
        )
        db.commit()
        out = qa_run_service.QaRunService.handle_chat(
            db,
            thread_id=thread_id,
            text=f"create a draft based on these companies you found to send to sanjay{tag} on Teams",
        )
        assert out == {"handled": True}
        assert seen["context"]["my_work_results"][0]["results"] == [
            {"Company": "Miro", "Website": "miro.com"}
        ]
        assert "chief of staff" in seen["prompt"] and "never as a chief of staff" in seen["prompt"]
        job = db.scalar(select(AgentJob).where(AgentJob.thread_id == thread_id))
        proposal = db.scalar(select(ActionProposal).where(ActionProposal.job_id == job.id))
        assert "miro.com" in proposal.body
