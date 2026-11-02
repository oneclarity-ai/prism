"""A QA tester Prism: plan card, live computer panel and the report, against a fake testing workspace."""

from __future__ import annotations

import uuid

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.test_prism_directory import open_sidebar_if_narrow


def seed_qa_prism(name: str) -> None:
    from app.db.session import SessionLocal
    from app.models.enums import PrismLifecycleState
    from app.schemas.prism_v22 import PrismCreate
    from app.services.prism_lifecycle_service import PrismLifecycleService

    with SessionLocal() as db:
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(name=name, description="Tests our websites.", template_key="qa_tester"),
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


def test_qa_tester_plans_runs_shows_its_screen_and_reports(
    page: Page, e2e_app, monkeypatch
) -> None:
    from app.core.config import get_settings
    from app.models.qa import QaRun
    from app.services import qa_run_service
    from app.services.qa_swarm_client import QaSwarmClient
    from tests.test_qa_tester_integration import FakeSwarm

    monkeypatch.setenv("QA_SWARM_URL", "http://swarm.invalid")
    monkeypatch.setenv("QA_SWARM_EMAIL", "tester@example.com")
    monkeypatch.setenv("QA_SWARM_PASSWORD", "secret-password")
    get_settings.cache_clear()
    fake = FakeSwarm()
    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(fake)),
    )
    name = f"Quinn {uuid.uuid4().hex[:5]}"
    seed_qa_prism(name)
    page.reload()
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name=name).first.click()

    expect(page.locator("#agent-computer-button")).to_be_visible()
    page.locator("#agent-message-input").fill("test example.com and check the contact form")
    page.locator("#agent-send-button").click()

    plan = page.locator(".qa-plan").last
    expect(plan).to_contain_text("example.com")
    expect(plan).to_contain_text("Live site · read-only")
    expect(plan).to_contain_text("Bug filing")
    plan.get_by_role("button", name="Start testing").click()

    panel = page.locator("#qa-computer-panel")
    expect(panel).to_have_class(__import__("re").compile(r"open"))
    fake.add_event(
        "tool_call",
        {"tool": "browser_navigate", "arguments": {"url": "https://example.com/contact"}},
    )
    fake.add_event("tool_call", {"tool": "browser_click", "arguments": {"element": "Send"}})
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        run = db.query(QaRun).order_by(QaRun.created_at.desc()).first()
        qa_run_service.QaRunService.sync(db, run.id)
    expect(panel).to_contain_text("Clicking 'Send'")
    expect(panel.locator(".qa-address")).to_contain_text("example.com/contact")

    fake.cases = [
        {
            "id": "c1",
            "title": "Empty email rejected",
            "given": "the form",
            "when": "submitted empty",
            "then": "an error shows",
            "status": "fail",
            "notes": "no error",
            "evidence_artifact_ids": [],
        }
    ]
    fake.status = "succeeded"
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run.id)
    expect(page.locator(".qa-report").last).to_contain_text("1 failed", timeout=15000)
    expect(page.locator(".qa-report").last).to_contain_text("Empty email rejected")
    # Nothing on the page names the testing workspace.
    expect(page.locator("body")).not_to_contain_text("swarm")
