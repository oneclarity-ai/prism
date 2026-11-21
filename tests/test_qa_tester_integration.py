from __future__ import annotations

import json
import os
import re
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.llm_usage import LLMUsage
from app.models.prism_v22 import Prism
from app.models.qa import QaApproval, QaRun
from app.schemas.prism_v22 import PrismCreate
from app.services import qa_run_service
from app.services.prism_conversation_service import PrismConversationService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.qa_plan_service import environment_for, find_site, looks_like_test_request
from app.services.qa_swarm_client import QaSwarmClient

SWARM_URL = "http://swarm.invalid:8080"


class FakeSwarm:
    """Just enough of the testing workspace to drive Prism through a whole run."""

    def __init__(self) -> None:
        self.logins = 0
        self.expire_next = False
        self.targets: list[dict] = []
        self.tasks: list[dict] = []
        self.started: list[dict] = []
        self.status = "running"
        self.error: str | None = None
        self.events: list[dict] = []
        self.cases: list[dict] = []
        self.bugs: list[dict] = []
        self.artifacts: list[dict] = []
        self.approvals: list[dict] = []
        self.cancelled = False
        self.run_id = "run-1"
        self.decisions: list[tuple[str, str]] = []
        self.cost = "0.2500"
        self.run_list: list[dict] = []
        self.run_operations: dict[str, str] = {}
        self.drop_run_response_once = False

    def add_event(self, type_: str, payload: dict) -> None:
        self.events.append(
            {"seq": len(self.events) + 1, "type": type_, "payload": payload, "created_at": "now"}
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        method = request.method
        body = json.loads(request.content) if request.content else {}
        if path == "/auth/login":
            self.logins += 1
            return httpx.Response(200, json={"id": "u"})
        if self.expire_next:
            self.expire_next = False
            return httpx.Response(401, json={"error": {"code": "unauthorized"}})
        if path == "/runtime/status":
            return httpx.Response(200, json={"workers_online": 1})
        if path == "/agents":
            return httpx.Response(200, json=[{"id": "agent-1", "name": "QA Agent"}])
        if path == "/targets" and method == "GET":
            return httpx.Response(200, json=self.targets)
        if path == "/targets":
            target = {"id": f"target-{len(self.targets) + 1}", **body}
            self.targets.append(target)
            return httpx.Response(201, json=target)
        if path == "/tasks":
            if body.get("operation_key"):
                old = next(
                    (t for t in self.tasks if t.get("operation_key") == body["operation_key"]), None
                )
                if old:
                    return httpx.Response(201, json=old)
            task = {"id": f"task-{len(self.tasks) + 1}", **body}
            self.tasks.append(task)
            return httpx.Response(201, json=task)
        if re.fullmatch(r"/tasks/[^/]+/runs", path):
            key = body.get("operation_key")
            if key and key in self.run_operations:
                return httpx.Response(
                    201, json={"id": self.run_operations[key], "status": "queued"}
                )
            self.started.append(body)
            if key:
                self.run_operations[key] = self.run_id
            if self.drop_run_response_once:
                self.drop_run_response_once = False
                raise httpx.ReadTimeout("response lost after commit", request=request)
            return httpx.Response(201, json={"id": self.run_id, "status": "queued"})
        if path == "/runs":
            return httpx.Response(200, json=self.run_list)
        if re.fullmatch(r"/runs/[^/]+", path):
            return httpx.Response(
                200,
                json={
                    "id": path.split("/")[-1],
                    "status": self.status,
                    "summary": "done" if self.status == "succeeded" else "",
                    "error": self.error,
                    "cost_usd": self.cost,
                },
            )
        if path.endswith("/events"):
            after = int(request.url.params.get("after_seq", 0))
            return httpx.Response(200, json=[e for e in self.events if e["seq"] > after])
        if path.endswith("/artifacts"):
            return httpx.Response(200, json=self.artifacts)
        if path.endswith("/test-cases"):
            return httpx.Response(200, json=self.cases)
        if path.endswith("/bugs"):
            return httpx.Response(200, json=self.bugs)
        if path == "/approvals":
            return httpx.Response(200, json=self.approvals)
        if path.startswith("/approvals/") and path.endswith("/decision"):
            approval_id = path.split("/")[2]
            self.decisions.append((approval_id, body["decision"]))
            for item in self.approvals:
                if item["id"] == approval_id:
                    item["status"] = "approved" if body["decision"] == "approve" else "rejected"
            self.run_id = "run-2"
            self.status = "running"
            return httpx.Response(200, json={"approval": {}, "resume_run_id": "run-2"})
        if path.endswith("/cancel"):
            self.cancelled = True
            return httpx.Response(200, json={"status": "cancelled"})
        if path.startswith("/artifacts/") and path.endswith("/file"):
            return httpx.Response(
                200, content=b"\x89PNG fake", headers={"content-type": "image/png"}
            )
        return httpx.Response(404, json={"error": {"code": "not_found"}})


@pytest.fixture
def swarm(monkeypatch):
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    monkeypatch.setenv("QA_SWARM_URL", SWARM_URL)
    monkeypatch.setenv("QA_SWARM_EMAIL", "tester@example.com")
    monkeypatch.setenv("QA_SWARM_PASSWORD", "s3cret-pass")
    monkeypatch.setenv("QA_WATCHER_ENABLED", "false")
    get_settings.cache_clear()
    fake = FakeSwarm()
    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(fake)),
    )
    yield fake
    get_settings.cache_clear()


def _active_prism(
    db, template_key: str = "qa_tester", description: str = "QA tester for our sites."
) -> Prism:
    prism = PrismLifecycleService.create(
        db,
        PrismCreate(
            name=f"Quinn {uuid.uuid4().hex[:6]}", description=description, template_key=template_key
        ),
    )
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
def qa_prism(swarm):
    with SessionLocal() as db:
        prism = _active_prism(db)
        _, thread = PrismConversationService.canonical_thread(db, prism.id)
        ids = (prism.id, thread.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(QaRun).where(QaRun.prism_id == ids[0]))
        db.execute(delete(AgentThread).where(AgentThread.prism_id == ids[0]))
        prism = db.get(Prism, ids[0])
        if prism is not None:
            db.delete(prism)
        db.commit()


def _plan(db, thread_id, text="test oneclarity.ai, check pricing and the contact form validation"):
    result = qa_run_service.QaRunService.handle_chat(db, thread_id=thread_id, text=text)
    assert result["handled"]
    return db.get(QaRun, result["qa_run_id"])


def _messages(db, thread_id):
    return list(
        db.scalars(
            select(AgentThreadMessage)
            .where(AgentThreadMessage.thread_id == thread_id)
            .order_by(AgentThreadMessage.created_at)
        )
    )


def test_site_and_environment_detection() -> None:
    assert find_site("test oneclarity.ai please") == "https://oneclarity.ai"
    assert (
        find_site("check https://www.oneclarity.ai/pricing/.")
        == "https://www.oneclarity.ai/pricing"
    )
    assert find_site("try localhost:5173/login") == "http://localhost:5173/login"
    assert find_site("open config.json and main.py") is None
    assert environment_for("https://www.oneclarity.ai") == "production"
    assert environment_for("https://staging.oneclarity.ai") == "staging"
    assert environment_for("http://localhost:5173") == "local"
    assert looks_like_test_request("test oneclarity.ai")
    assert looks_like_test_request("can you test the website?")
    assert not looks_like_test_request("good morning, how are you")


def test_a_test_request_becomes_a_plan_card_that_is_safe_by_default(qa_prism) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        assert run.state == "planned"
        plan = run.plan
        assert plan["site"] == "https://oneclarity.ai"
        assert plan["environment"] == "production"
        assert plan["allow_bug_filing"] is False
        assert "Use synthetic test data only" in plan["notes"]
        assert plan["discovery_mode"] == "automatic"
        assert plan["allowed_origins"] == ["https://oneclarity.ai"]
        assert plan["max_turns"] <= 150 and plan["budget_usd"] <= 3
        card = _messages(db, thread_id)[-1]
        assert card.message_metadata["kind"] == "qa_plan"
        assert card.message_metadata["qa_run_id"] == str(run.id)


def test_only_qa_prisms_take_test_requests_and_a_missing_site_is_asked_for(qa_prism, swarm) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="test the website"
        )
        assert out["handled"] and "qa_run_id" not in out
        assert "Which site" in _messages(db, thread_id)[-1].content
        # Small talk with no model available falls back to the normal chat, never to Teams here.
        out = qa_run_service.QaRunService.handle_chat(db, thread_id=thread_id, text="good morning")
        assert out == {"handled": False}

        other = _active_prism(db, template_key="blank", description="Sales ops lead.")
        _, other_thread = PrismConversationService.canonical_thread(db, other.id)
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=other_thread.id, text="test oneclarity.ai"
        )
        assert out == {"handled": False}
        db.execute(delete(AgentThread).where(AgentThread.prism_id == other.id))
        db.delete(db.get(Prism, other.id))
        db.commit()


def test_a_missing_workspace_is_explained_in_the_prisms_voice(qa_prism, monkeypatch) -> None:
    prism_id, thread_id = qa_prism
    monkeypatch.setenv("QA_SWARM_URL", "")
    get_settings.cache_clear()
    with SessionLocal() as db:
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="test oneclarity.ai"
        )
        assert out["handled"]
        assert "isn't set up" in _messages(db, thread_id)[-1].content


def test_a_run_is_followed_live_and_ends_with_a_report(qa_prism, swarm) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        started = qa_run_service.QaRunService.start(
            db, run.id, {"max_turns": 9999, "budget_usd": 99, "allow_bug_filing": True}
        )
        assert started.state == "running"
        # Edits are clamped by the server, and production is never filed on.
        assert started.plan["max_turns"] == get_settings().qa_max_turns_cap
        assert started.plan["budget_usd"] == get_settings().qa_budget_cap_usd
        assert started.plan["allow_bug_filing"] is False
        assert swarm.targets[0]["environment"] == "production"
        assert swarm.tasks[0]["scope"]["allow_bug_filing"] is False
        assert swarm.tasks[0]["scope"]["discovery_mode"] == "automatic"
        assert swarm.started[0]["mode"] == "single"
        run_id = run.id

        swarm.expire_next = True  # the session expires mid-run: Prism signs in again by itself
        swarm.add_event(
            "tool_call",
            {"tool": "browser_navigate", "arguments": {"url": "https://oneclarity.ai/pricing"}},
        )
        swarm.add_event(
            "tool_call", {"tool": "browser_click", "arguments": {"element": "Book a demo"}}
        )
        swarm.add_event("artifact", {"kind": "screenshot", "artifact_id": "art-1", "file": "a.png"})
        swarm.cases = [
            {
                "id": "c1",
                "title": "Pricing loads",
                "given": "g",
                "when": "w",
                "then": "t",
                "status": "pass",
                "notes": "",
                "evidence_artifact_ids": ["art-1"],
            },
            {
                "id": "c2",
                "title": "Empty email rejected",
                "given": "g",
                "when": "w",
                "then": "t",
                "status": "fail",
                "notes": "no error shown",
                "evidence_artifact_ids": ["art-1"],
            },
        ]
        qa_run_service.QaRunService.sync(db, run_id)
        view = qa_run_service.QaRunService.snapshot(db, db.get(QaRun, run_id))
        assert view["current_url"] == "https://oneclarity.ai/pricing"
        assert view["activity"] == "Clicking 'Book a demo'"
        assert view["screen"] == 0
        assert view["cases"]["pass"] == 1 and view["cases"]["fail"] == 1
        assert swarm.logins == 3  # start, sync, and one re-login after the 401

        swarm.artifacts = [
            {"id": "art-1", "kind": "screenshot"},
            {"id": "art-2", "kind": "screenshot"},
        ]
        swarm.bugs = [
            {
                "id": "b1",
                "title": "Empty email rejected",
                "severity": "high",
                "steps": "1. submit",
                "expected": "error",
                "actual": "nothing",
                "status": "draft",
            }
        ]
        swarm.status = "succeeded"
        qa_run_service.QaRunService.sync(db, run_id)
        db.expire_all()
        done = db.get(QaRun, run_id)
        assert done.state == "succeeded"
        report = qa_run_service.QaRunService.snapshot(db, done)["report"]
        assert report["counts"] == {"total": 2, "pass": 1, "fail": 1, "blocked": 0, "skipped": 0}
        assert report["bugs"][0]["severity"] == "high" and report["bugs"][0]["screens"] == [0]
        assert report["cases"][1]["screens"] == [0]
        assert float(done.cost_usd) == 0.25
        final = _messages(db, thread_id)[-1]
        assert final.message_metadata["kind"] == "qa_report"
        assert "1 of 2" in final.content or "oneclarity" in final.content
        # The proxy serves the screenshot by plain number.
        data, content_type = qa_run_service.QaRunService.artifact(db, run_id, 1)
        assert data and content_type == "image/png"


def test_bug_filing_approvals_are_relayed_in_chat_and_the_run_resumes(qa_prism, swarm) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        run = _plan(db, thread_id, "test staging.example.com forms")
        started = qa_run_service.QaRunService.start(db, run.id)
        run_id = started.id
        swarm.bugs = [
            {
                "id": "b1",
                "title": "Typo in footer",
                "severity": "low",
                "steps": "look",
                "expected": "ok",
                "actual": "typo",
                "status": "draft",
            }
        ]
        swarm.status = "waiting_approval"
        swarm.approvals = [
            {
                "id": "ap-1",
                "run_id": "run-1",
                "action": "file_bug",
                "status": "pending",
                "payload": {"arguments": {"bug_id": "b1"}},
            }
        ]
        qa_run_service.QaRunService.sync(db, run_id)
        qa_run_service.QaRunService.sync(db, run_id)  # a second pass never duplicates the card
        db.expire_all()
        assert db.get(QaRun, run_id).state == "waiting_approval"
        approvals = list(db.scalars(select(QaApproval).where(QaApproval.qa_run_id == run_id)))
        assert len(approvals) == 1 and approvals[0].payload["title"] == "Typo in footer"
        cards = [
            m for m in _messages(db, thread_id) if m.message_metadata.get("kind") == "qa_approval"
        ]
        assert len(cards) == 1

        qa_run_service.QaRunService.decide(db, approvals[0].id, "approve")
        db.expire_all()
        resumed = db.get(QaRun, run_id)
        assert resumed.state == "running" and resumed.swarm_run_id == "run-2"
        assert swarm.decisions == [("ap-1", "approve")]


def test_cancel_stops_the_run_and_says_so(qa_prism, swarm) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        qa_run_service.QaRunService.start(db, run.id)
        qa_run_service.QaRunService.cancel(db, run.id)
        db.expire_all()
        assert db.get(QaRun, run.id).state == "cancelled" and swarm.cancelled
        # A new test may start once the last one has stopped.
        second = _plan(db, thread_id, "test example.org")
        assert qa_run_service.QaRunService.start(db, second.id).state == "running"


def test_only_one_test_runs_at_a_time_per_prism(qa_prism, swarm) -> None:
    from app.services.errors import RuleViolationError

    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        first = _plan(db, thread_id)
        qa_run_service.QaRunService.start(db, first.id)
        second = _plan(db, thread_id, "test example.org")
        with pytest.raises(RuleViolationError):
            qa_run_service.QaRunService.start(db, second.id)


def test_nothing_a_browser_can_see_names_the_testing_workspace(qa_prism, swarm) -> None:
    monkey_headers = {}
    prism_id, thread_id = qa_prism
    client = TestClient(app)
    with SessionLocal() as db:
        run_id = _plan(db, thread_id).id
    swarm.add_event(
        "tool_call", {"tool": "browser_navigate", "arguments": {"url": "https://oneclarity.ai"}}
    )
    swarm.add_event(
        "artifact", {"kind": "screenshot", "artifact_id": "art-secret-9", "file": "a.png"}
    )
    assert client.get("/api/v2/qa/status").json() == {
        "available": True,
        "reason": None,
        "computers": False,
    }
    started = client.post(f"/api/v2/qa/runs/{run_id}/start", json={})
    assert started.status_code == 200, started.text
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    bodies = [
        started.text,
        client.get(f"/api/v2/qa/runs/{run_id}").text,
        client.get(f"/api/v2/prisms/{prism_id}/qa/runs").text,
        json.dumps(
            [
                m["message_metadata"]
                for m in client.get(f"/api/v2/agent/threads/{thread_id}/messages").json()
            ]
        ),
    ]
    for body in bodies:
        for secret in (
            "swarm.invalid",
            "s3cret-pass",
            "tester@example.com",
            "art-secret-9",
            "task-1",
            "target-1",
            "run-1",
            "agent-1",
        ):
            assert secret not in body, secret
    shot = client.get(f"/api/v2/qa/runs/{run_id}/screens/0", headers=monkey_headers)
    assert shot.status_code == 200 and shot.headers["content-type"] == "image/png"
    assert client.get(f"/api/v2/qa/runs/{run_id}/screens/7").status_code == 404
    with SessionLocal() as db:
        qa_run_service.QaRunService.cancel(db, run_id)


def test_unreachable_workspace_stays_reconcilable_with_a_friendly_status(
    qa_prism, monkeypatch
) -> None:
    prism_id, thread_id = qa_prism

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused http://swarm.invalid:8080")

    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(boom)),
    )
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        pending = qa_run_service.QaRunService.start(db, run.id)
        assert pending.state == "starting"
        assert pending.current_activity == "Reconciling with my workspace…"
        assert "swarm.invalid" not in (pending.error or "")
        snapshot = qa_run_service.QaRunService.snapshot(db, pending)
        assert "testing has not started" in snapshot["startup_warning"]
        assert "swarm.invalid" not in json.dumps(snapshot)


def test_qa_tester_onboarding_asks_testing_questions_and_agreement_allows_bug_filing(swarm) -> None:
    from app.services.prism_onboarding_service import PrismOnboardingService

    with SessionLocal() as db:
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(
                name=f"Quinn {uuid.uuid4().hex[:6]}",
                description="Tests sites.",
                template_key="qa_tester",
            ),
        )
        try:
            session = PrismOnboardingService.start(db, prism.id)
            prompts = {q.key: q for q in session["questions"]}
            assert "Which sites will I test" in prompts["mission"].prompt
            assert "House rules for testing" in prompts["restrictions"].prompt
            labels = [c["label"] for c in prompts["allowed_proposals"].choices]
            assert (
                "File bugs for my approval" in labels and "Run website tests when you ask" in labels
            )
            assert "QA Tester" in prompts["mission"].help_text
        finally:
            db.execute(delete(AgentThread).where(AgentThread.prism_id == prism.id))
            db.commit()
            db.delete(db.get(Prism, prism.id))
            db.commit()


def _finished_run(db, prism_id, thread_id) -> QaRun:
    run = QaRun(
        prism_id=prism_id,
        thread_id=thread_id,
        state="succeeded",
        plan={"host": "example.com", "site": "https://example.com"},
        report={
            "counts": {"total": 2, "pass": 1, "fail": 1, "blocked": 0, "skipped": 0},
            "cases": [
                {"title": "Empty email rejected", "status": "fail", "notes": "no error shown"},
                {"title": "Home loads", "status": "pass", "notes": ""},
            ],
            "bugs": [
                {
                    "title": "Contact form accepts empty email",
                    "severity": "high",
                    "steps": "submit empty",
                    "expected": "an error",
                    "actual": "nothing happens",
                }
            ],
            "summary": "one failure",
        },
    )
    db.add(run)
    db.commit()
    return run


def test_follow_up_questions_are_answered_from_test_results_never_from_teams(qa_prism) -> None:
    from app.models.agent_v21 import AgentJob

    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        _finished_run(db, prism_id, thread_id)
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="what changes do you suggest we should focus on"
        )
        assert out == {"handled": True}
        reply = _messages(db, thread_id)[-1]
        assert reply.role == "assistant" and reply.job_id is None
        assert "Contact form accepts empty email" in reply.content
        assert "Empty email rejected" in reply.content
        assert db.scalar(select(AgentJob.id).where(AgentJob.thread_id == thread_id)) is None


def test_a_qa_prism_with_no_results_says_so_and_teams_questions_still_go_to_teams(qa_prism) -> None:
    prism_id, thread_id = qa_prism
    with SessionLocal() as db:
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="what should we fix first?"
        )
        assert out == {"handled": True}
        assert "haven't tested anything yet" in _messages(db, thread_id)[-1].content
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="summarize my Teams chats from today"
        )
        assert out == {"handled": False}


def test_the_model_answer_is_used_when_available_and_can_hand_off(qa_prism) -> None:
    from app.services.llm_provider import FakeLLMProvider, ProviderResult
    from app.services.llm_service import LLMService

    prism_id, thread_id = qa_prism

    def provider(payload: dict) -> FakeLLMProvider:
        class Scripted(FakeLLMProvider):
            def generate_structured(self, **kwargs):
                self.requests.append(kwargs)
                return ProviderResult(text=json.dumps(payload), model="fake-model")

        return Scripted()

    with SessionLocal() as db:
        _finished_run(db, prism_id, thread_id)
        LLMService.provider_override = provider(
            {"reply": "Fix the contact form first.", "needs_other_help": False}
        )
        try:
            out = qa_run_service.QaRunService.handle_chat(
                db, thread_id=thread_id, text="what next?"
            )
            assert out == {"handled": True}
            assert _messages(db, thread_id)[-1].content == "Fix the contact form first."
            LLMService.provider_override = provider({"reply": "", "needs_other_help": True})
            out = qa_run_service.QaRunService.handle_chat(
                db, thread_id=thread_id, text="hey, how is your day"
            )
            assert out == {"handled": False}
        finally:
            LLMService.provider_override = None


def test_a_draft_for_a_colleague_is_an_editable_draft_card_that_can_be_sent(
    qa_prism, monkeypatch
) -> None:
    from types import SimpleNamespace

    from app.models.agent_v21 import ActionProposal, AgentJob
    from app.models.employee import Employee
    from app.schemas.agent_sources import TeamsChatSourceRead
    from app.services.teams_read_service import TeamsReadService

    prism_id, thread_id = qa_prism
    tag = uuid.uuid4().hex[:6]
    chat_id = f"chat-{tag}"
    sent: list[tuple[str, str]] = []
    signatures: list[str | None] = []

    class FakeGraph:
        def __init__(self, *_: object) -> None: ...

        def send_chat_message(self, chat: str, content: str, signature: str | None = None) -> dict:
            sent.append((chat, content))
            signatures.append(signature)
            return {"id": "msg-1", "createdDateTime": "2026-11-02T10:00:00Z"}

    monkeypatch.setattr(
        TeamsReadService,
        "list_sources",
        staticmethod(
            lambda db: [
                TeamsChatSourceRead(
                    external_id=chat_id,
                    label=f"Akshay{tag} Aher",
                    chat_type="private",
                    participants=[f"Akshay{tag} Aher"],
                )
            ]
        ),
    )
    for module in ("approved_teams_execution_service",):
        monkeypatch.setattr(
            f"app.services.{module}.MicrosoftService.get_connection",
            lambda _db: SimpleNamespace(microsoft_user_id="manager"),
        )
        monkeypatch.setattr(f"app.services.{module}.MicrosoftGraphClient", FakeGraph)

    with SessionLocal() as db:
        akshay = Employee(
            name=f"Akshay{tag} Aher", email=f"akshay{tag}@example.com", role="Team member"
        )
        db.add(akshay)
        db.commit()
        try:
            _finished_run(db, prism_id, thread_id)
            out = qa_run_service.QaRunService.handle_chat(
                db,
                thread_id=thread_id,
                text=f"create a report of this and create a draft message to send to akshay{tag}",
            )
            assert out == {"handled": True}
            job = db.scalar(select(AgentJob).where(AgentJob.thread_id == thread_id))
            assert job is not None and job.state.value == "waiting_for_approval"
            proposal = db.scalar(select(ActionProposal).where(ActionProposal.job_id == job.id))
            assert proposal.destination["chat_id"] == chat_id
            assert "Contact form accepts empty email" in proposal.body
            assert "Subject:" not in proposal.body
            card = _messages(db, thread_id)[-1]
            assert card.job_id == job.id and card.message_metadata["kind"] == "conversation_review"
            job_id, proposal_id = job.id, proposal.id
        finally:
            pass

    client = TestClient(app)
    review = client.get(f"/api/v2/agent/jobs/{job_id}/review").json()
    assert review["proposal"]["state"] == "pending"
    # Edit it, approve exactly what is on screen, and send it.
    revised = client.post(
        f"/api/v2/agent/proposals/{proposal_id}/revisions",
        json={"body": "Hi Akshay, edited by me.", "reason": "edit"},
    ).json()
    decided = client.post(
        f"/api/v2/agent/proposals/{revised['id']}/decision",
        json={
            "decision": "approved",
            "expected_revision": revised["revision"],
            "expected_payload_hash": revised["payload_hash"],
        },
    )
    assert decided.status_code == 200, decided.text
    sent_response = client.post(f"/api/v2/agent/proposals/{revised['id']}/execution")
    assert sent_response.status_code in (200, 201), sent_response.text
    assert sent == [(chat_id, "Hi Akshay, edited by me.")]
    # The recipient is told which Prism wrote it, not just "Prism".
    with SessionLocal() as db:
        prism_name = db.get(Prism, prism_id).name
    assert signatures and signatures[0].startswith("Sent by ")
    assert signatures[0].endswith(f"{prism_name} Prism"), signatures

    with SessionLocal() as db:
        # Asking what someone said still needs Teams.
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text=f"what did akshay{tag} reply?"
        )
        assert out == {"handled": False}
        db.delete(db.get(Employee, akshay.id))
        db.commit()


def test_without_a_teams_chat_the_draft_text_is_still_shown(qa_prism, monkeypatch) -> None:
    from app.services.teams_read_service import TeamsReadService

    prism_id, thread_id = qa_prism
    monkeypatch.setattr(TeamsReadService, "list_sources", staticmethod(lambda db: []))
    with SessionLocal() as db:
        _finished_run(db, prism_id, thread_id)
        out = qa_run_service.QaRunService.handle_chat(
            db, thread_id=thread_id, text="write up the results and draft a message to nobody"
        )
        assert out == {"handled": True}
        last = _messages(db, thread_id)[-1].content
        assert "couldn't find a Teams chat" in last and "Contact form accepts empty email" in last


def test_cost_shows_live_while_running_not_only_at_the_end(qa_prism, swarm) -> None:
    _, thread_id = qa_prism
    swarm.cost = "0.0000"  # the workspace saves a run's cost only when it ends
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        qa_run_service.QaRunService.start(db, run.id, {})
        swarm.add_event("usage", {"cost_usd": 0.0123, "turn": 4})
        synced = qa_run_service.QaRunService.sync(db, run.id)
        assert float(synced.cost_usd) == pytest.approx(0.0123)
        swarm.cost, swarm.status = "0.0150", "succeeded"
        synced = qa_run_service.QaRunService.sync(db, run.id)
        assert float(synced.cost_usd) == pytest.approx(0.0150)


def test_workspace_spend_is_copied_into_usage_once_and_categorised(qa_prism, swarm) -> None:
    from app.services.qa_spend_service import (
        FEATURE_OTHER,
        FEATURE_PRISM,
        PROVIDER,
        QaSpendService,
    )

    _, thread_id = qa_prism
    tag = uuid.uuid4().hex[:8]
    mine, other, live = f"run-{tag}-a", f"run-{tag}-b", f"run-{tag}-c"
    swarm.run_id = mine
    with SessionLocal() as db:
        run = _plan(db, thread_id)
        qa_run_service.QaRunService.start(db, run.id, {})
    base = {
        "input_tokens": 1000,
        "cached_input_tokens": 400,
        "output_tokens": 50,
        "model": "gpt-5-mini",
    }
    when = {"started_at": "2026-11-02T10:00:00+00:00", "ended_at": "2026-11-02T10:05:00+00:00"}
    swarm.run_list = [
        {"id": mine, "status": "succeeded", "cost_usd": "0.0321", **base, **when},
        {"id": other, "status": "failed", "cost_usd": "0.1603", **base, **when},
        {"id": live, "status": "running", "cost_usd": "0.0000", **base, **when},
    ]
    keys = [f"qa-run:{i}" for i in (mine, other, live)]
    try:
        with SessionLocal() as db, qa_run_service.make_client() as client:
            assert QaSpendService.sync(db, client) == 2
            assert QaSpendService.sync(db, client) == 0  # syncing again never double counts
            rows = {
                row.request_id: row
                for row in db.scalars(select(LLMUsage).where(LLMUsage.request_id.in_(keys)))
            }
        assert set(rows) == set(keys[:2])  # a run still in progress waits for a later sync
        assert rows[keys[0]].feature == FEATURE_PRISM
        assert rows[keys[1]].feature == FEATURE_OTHER
        assert rows[keys[0]].provider == PROVIDER
        assert rows[keys[0]].model == "gpt-5-mini"
        # priced from tokens at the model's rates: 600 fresh + 400 cached input, 50 output
        assert float(rows[keys[0]].estimated_total_cost_usd) == pytest.approx(0.00026)
        assert rows[keys[0]].cached_input_tokens == 400
        assert rows[keys[0]].pricing_snapshot["swarm_cost_usd"] == "0.0321"
        assert rows[keys[0]].latency_ms == 300000
    finally:
        with SessionLocal() as db:
            db.execute(delete(LLMUsage).where(LLMUsage.request_id.in_(keys)))
            db.commit()


def test_a_draft_for_several_people_in_a_group_is_a_card_not_text(qa_prism, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.models.agent_v21 import ActionProposal, AgentJob
    from app.schemas.agent_sources import TeamsChatSourceRead
    from app.services import llm_service
    from app.services.prism_teams_policy_service import PrismTeamsPolicyService

    prism_id, thread_id = qa_prism
    tag = uuid.uuid4().hex[:6]
    group = TeamsChatSourceRead(
        external_id=f"group-{tag}",
        label="Website crew",
        chat_type="group",
        participants=[f"Sanjay{tag} K", f"Ajay{tag} S", "Yash Mandi"],
    )
    bigger = TeamsChatSourceRead(
        external_id=f"big-{tag}",
        label="Everyone",
        chat_type="group",
        participants=[f"Sanjay{tag} K", f"Ajay{tag} S", "A", "B", "C"],
    )
    private = TeamsChatSourceRead(
        external_id=f"dm-{tag}",
        label=f"Sanjay{tag} K",
        chat_type="private",
        participants=[f"Sanjay{tag} K"],
    )
    monkeypatch.setattr(
        PrismTeamsPolicyService,
        "allowed_sources",
        staticmethod(lambda db, prism_id: (None, [bigger, private, group])),
    )
    answer = qa_run_service._Answer(
        reply="Here's a draft for Sanjay and Ajay. Edit it and send when you're ready.",
        draft_to=f"Sanjay{tag} and Ajay{tag}",
        draft_body="Hi both,\nThe website test finished: one issue to look at.",
    )
    monkeypatch.setattr(llm_service.LLMService, "complete", staticmethod(lambda **_: answer))

    with SessionLocal() as db:
        _finished_run(db, prism_id, thread_id)
        out = qa_run_service.QaRunService.handle_chat(
            db,
            thread_id=thread_id,
            text=f"draft a message to sanjay{tag} and ajay{tag} in our group about the website testing report",
        )
        assert out == {"handled": True}
        job = db.scalar(select(AgentJob).where(AgentJob.thread_id == thread_id))
        assert job is not None and job.state.value == "waiting_for_approval"
        proposal = db.scalar(select(ActionProposal).where(ActionProposal.job_id == job.id))
        assert proposal.destination["chat_id"] == f"group-{tag}"  # the closest group, not the DM
        assert proposal.body.startswith("Hi both")
        card = _messages(db, thread_id)[-1]
        assert card.message_metadata["kind"] == "conversation_review"

        # A single name still goes to the person's own chat.
        assert (
            qa_run_service.QaRunService._find_chat(
                db, SimpleNamespace(id=prism_id), f"Sanjay{tag}"
            ).external_id
            == f"dm-{tag}"
        )
