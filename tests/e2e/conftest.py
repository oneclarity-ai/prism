"""Browser end-to-end harness: the real UI and API on a scratch Postgres schema.

Microsoft Graph and the model provider are replaced by deterministic fakes, and every credential
from `.env` is blanked, so these tests cannot reach Microsoft or a model vendor. Opt in with
`RUN_E2E=1 pytest tests/e2e` (a separate invocation: the app binds to one database per process).
Needs Google Chrome; set E2E_BROWSER_CHANNEL to use another Playwright channel.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

if os.getenv("RUN_E2E") != "1":
    collect_ignore_glob = ["test_*.py"]

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_SCHEMA = "prism_e2e"


def _scratch_url() -> str:
    """The configured server with search_path pinned to a private schema.

    The role in `.env` usually cannot CREATE DATABASE, so isolation is a dedicated schema: every
    table, the alembic version row, and all test data live there and never touch dev tables.
    """
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    # Read the file directly: an exported DATABASE_URL (or the unit-test default) must not win.
    source = os.getenv("E2E_SOURCE_DATABASE_URL") or dotenv_values(ROOT / ".env").get(
        "DATABASE_URL"
    )
    if not source:
        raise RuntimeError("Set E2E_SOURCE_DATABASE_URL or DATABASE_URL in .env to locate Postgres")
    base = make_url(source).set(query={}).render_as_string(hide_password=False)
    # Unencoded on purpose: alembic's ConfigParser rejects the '%' that URL-encoding would add.
    return f"{base}?options=-csearch_path={SCRATCH_SCHEMA}"


def _recent(hours_ago: float) -> str:
    """Graph timestamps relative to now, so fixtures never age out of the 1-day Teams window."""
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGraph:
    """Stands in for MicrosoftGraphClient for both reads and the approved send."""

    sent: list[tuple[str, str]] = []
    fail_sends_for: set[str] = set()
    hide_chats = False
    read_error: Exception | None = None
    empty_chats = False
    hostile = False

    CHATS = {
        "chat-parv": ("oneOnOne", None, [("parv", "Parv Pareek")]),
        "chat-meera": ("oneOnOne", None, [("meera", "Meera Shah")]),
        "chat-release": (
            "group",
            "Release group",
            [("parv", "Parv Pareek"), ("meera", "Meera Shah"), ("rohan", "Rohan Das")],
        ),
    }
    MESSAGES = {
        "chat-parv": "Release is ready on Friday, can you confirm the schema?",
        "chat-meera": "Frontend is blocked until the schema is documented.",
        "chat-release": "Should QA delay today's regression run?",
    }

    def __init__(self, _db, _connection) -> None:
        pass

    def list_chats(self):
        if FakeGraph.read_error:
            raise FakeGraph.read_error
        if FakeGraph.hide_chats:
            return []
        return [
            {
                "id": chat_id,
                "chatType": kind,
                "topic": topic,
                "lastUpdatedDateTime": _recent(1 + index),
                "members": [{"userId": "manager", "displayName": "Manager"}]
                + [{"userId": uid, "displayName": name} for uid, name in members],
            }
            for index, (chat_id, (kind, topic, members)) in enumerate(self.CHATS.items())
        ]

    def list_chat_messages(self, chat_id: str, *, limit: int):
        if FakeGraph.empty_chats:
            return []
        _, _, members = self.CHATS[chat_id]
        uid, name = members[0]
        if FakeGraph.hostile:
            body = {
                "contentType": "html",
                "content": '<p>Ping</p><img src=x onerror="window.__xss=1"><script>window.__xss=1</script>',
            }
        else:
            body = {"contentType": "text", "content": self.MESSAGES[chat_id]}
        return [
            {
                "id": f"{chat_id}-message-1",
                "messageType": "message",
                "createdDateTime": _recent(0.5),
                "from": {"user": {"id": uid, "displayName": name}},
                "body": body,
            }
        ]

    def send_chat_message(self, chat_id: str, content: str, signature: str | None = None):
        if chat_id in FakeGraph.fail_sends_for:
            from app.services.errors import ExternalServiceError

            raise ExternalServiceError("Microsoft rejected the message")
        FakeGraph.sent.append((chat_id, content))
        return {"id": f"sent-{len(FakeGraph.sent)}", "createdDateTime": _recent(0)}


def _review_json(context: dict) -> str:
    """Build a schema-valid review that cites only the evidence the request actually contained."""
    if context.get("mode") == "instruction_only":
        sources = context["selected_sources"]
        return json.dumps(
            {
                "summary": "Drafted from your instruction; no Teams messages were available.",
                "proposed_actions": [
                    {
                        "destination_source_id": source["external_id"],
                        "body": f"Hi {source['label'].split()[0]}, please complete the planned items.",
                        "reason": "You asked for this message; no chat history exists.",
                        "sequence": index + 1,
                        "depends_on_source_ids": [],
                    }
                    for index, source in enumerate(sources)
                ],
                "action_plan_summary": "Messages from your instruction",
                "confidence": 0.7,
                "limitations": [],
                "applied_preference_ids": [],
            }
        )
    evidence = context["evidence"]
    ids = [item["evidence_id"] for item in evidence]
    goal = context["manager_goal"].lower()
    sources = context["selected_sources"]
    if "draft" in goal and len(sources) > 1:
        by_source = {item["source_external_id"]: item["evidence_id"] for item in evidence}
        actions = [
            {
                "destination_source_id": source["external_id"],
                "body": f"Hi {source['label'].split()[0]}, please confirm your update.",
                "reason": f"{source['label']} raised an open item.",
                "evidence_ids": [by_source[source["external_id"]]],
                "sequence": index + 1,
                "depends_on_source_ids": [],
            }
            for index, source in enumerate(sources)
            if source["external_id"] in by_source
        ]
        return json.dumps(
            {
                "summary": "Both people are waiting on a follow-up from you.",
                "summary_evidence_ids": ids,
                "attention_items": [],
                "manager_questions": [],
                "requires_reply": True,
                "proposed_reply": None,
                "action_plan_summary": "Follow up with each person",
                "proposed_actions": actions,
                "confidence": 0.9,
                "limitations": [],
                "applied_preference_ids": [],
            }
        )
    summary = "The release schema is the open dependency."
    if FakeGraph.hostile:
        summary += ' <img src=x onerror="window.__xss=1"><b>bold</b>'
    return json.dumps(
        {
            "summary": summary,
            "summary_evidence_ids": ids,
            "attention_items": [
                {
                    "title": "Schema blocks the frontend",
                    "detail": "Work depends on the documented response schema.",
                    "evidence_ids": ids[:1],
                    "kind": "direct",
                    "source_external_ids": [evidence[0]["source_external_id"]],
                }
            ],
            "manager_questions": [],
            "requires_reply": False,
            "proposed_reply": None,
            "confidence": 0.85,
            "limitations": [],
            "applied_preference_ids": [],
        }
    )


@pytest.fixture(scope="session")
def e2e_app():
    scratch_url = _scratch_url()
    from sqlalchemy import create_engine, text

    admin = create_engine(scratch_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))

    env = {
        "DATABASE_URL": scratch_url,
        "PRISM_V21_ENABLED": "true",
        "PRISM_V22_ENABLED": "true",
        "PRISM_V22_SINGLE_EXECUTIVE_MODE": "false",
        "AUTOMATION_SCHEDULER_ENABLED": "false",
        "OPERATOR_API_TOKEN": "",
        "MICROSOFT_TENANT_ID": "",
        "MICROSOFT_CLIENT_ID": "",
        "MICROSOFT_CLIENT_SECRET": "",
        "MICROSOFT_WEBHOOK_BASE_URL": "",
        "INTELLIGENCE_LLM_ENABLED": "false",
    }
    os.environ.update(env)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ},
        check=True,
        capture_output=True,
    )

    import uvicorn

    from app.core.config import get_settings
    from app.main import app
    from app.services.llm_provider import FakeLLMProvider, ProviderResult
    from app.services.llm_service import LLMService

    get_settings.cache_clear()
    from app.db.session import SessionLocal

    # Never run browser tests against real tables: prove the app is pinned to the scratch schema.
    with SessionLocal() as db:
        assert db.execute(text("SHOW search_path")).scalar() == SCRATCH_SCHEMA
        assert db.execute(text("SELECT current_schema()")).scalar() == SCRATCH_SCHEMA

    patcher = pytest.MonkeyPatch()
    connection = lambda _db: SimpleNamespace(microsoft_user_id="manager")  # noqa: E731
    for module in ("teams_read_service", "approved_teams_execution_service"):
        patcher.setattr(f"app.services.{module}.MicrosoftService.get_connection", connection)
        patcher.setattr(f"app.services.{module}.MicrosoftGraphClient", FakeGraph)

    class ScriptedProvider(FakeLLMProvider):
        def generate_structured(self, **kwargs):
            self.requests.append(kwargs)
            return ProviderResult(text=_review_json(kwargs["context"]), model="fake-model")

    LLMService.provider_override = ScriptedProvider()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("e2e server did not start")
        time.sleep(0.05)
    yield SimpleNamespace(url=f"http://127.0.0.1:{port}", graph=FakeGraph)

    server.should_exit = True
    thread.join(timeout=10)
    LLMService.provider_override = None
    patcher.undo()
    from app.db.session import engine

    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
    admin.dispose()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(channel=os.getenv("E2E_BROWSER_CHANNEL", "chrome"))
        yield instance
        instance.close()


def reset_scratch_data() -> None:
    """Empty every scratch-schema table so each test starts from a clean conversation."""
    from sqlalchemy import text

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        assert db.execute(text("SELECT current_schema()")).scalar() == SCRATCH_SCHEMA
        tables = db.execute(
            text(
                "SELECT quote_ident(tablename) FROM pg_tables "
                "WHERE schemaname = :schema AND tablename <> 'alembic_version'"
            ),
            {"schema": SCRATCH_SCHEMA},
        ).scalars()
        names = ", ".join(f'"{SCRATCH_SCHEMA}".{name}' for name in tables)
        if names:
            # A request from the previous test may still be finishing (it can be waiting on its own
            # usage-log insert, which queues behind this TRUNCATE). Give up on the lock quickly and
            # retry, so the in-flight request can finish instead of both waiting on each other.
            from sqlalchemy.exc import OperationalError

            for attempt in range(8):
                try:
                    db.execute(text("SET LOCAL lock_timeout = '3s'"))
                    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
                    break
                except OperationalError:
                    db.rollback()
                    if attempt == 7:
                        raise
                    time.sleep(0.5)
        db.commit()


@pytest.fixture(params=[(1280, 900), (390, 780)], ids=["desktop", "narrow"])
def page(request, browser, e2e_app):
    """A fresh page at desktop and phone widths; data and fake sends are reset per test."""
    reset_scratch_data()
    FakeGraph.sent = []
    FakeGraph.fail_sends_for = set()
    FakeGraph.hide_chats = False
    FakeGraph.read_error = None
    FakeGraph.empty_chats = False
    FakeGraph.hostile = False
    width, height = request.param
    context = browser.new_context(base_url=e2e_app.url, viewport={"width": width, "height": height})
    # Land on the Agent workspace directly; the sidebar is collapsed at phone width.
    context.add_init_script("localStorage.setItem('manager-agent-tab', 'agent')")
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(f"{e2e_app.url}/dashboard/")
    yield page
    context.close()
