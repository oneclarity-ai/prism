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
    offline = {"enabled": False}

    def transport(request):
        if offline["enabled"]:
            raise httpx.ConnectError("Synthetic workspace outage")
        return fake(request)

    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(transport)),
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
    expect(plan).to_contain_text("Live site · dummy data")
    expect(plan).to_contain_text("Discover pages automatically")
    expect(plan).to_contain_text("Bug filing")
    offline["enabled"] = True
    plan.get_by_role("button", name="Start testing").click()

    panel = page.locator("#qa-computer-panel")
    expect(panel).to_have_class(__import__("re").compile(r"open"))
    expect(panel.locator(".qa-caption")).to_contain_text("Waiting for workspace")
    expect(panel).to_contain_text("testing has not started")
    expect(panel).not_to_contain_text("Starting my computer")

    # Recover the original approved start, without creating another run.
    offline["enabled"] = False
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        qa_run_service.QaRunService.cycle(db)
    expect(panel).not_to_contain_text("testing has not started")
    assert len(fake.started) == 1
    fake.add_event(
        "tool_call",
        {"tool": "browser_navigate", "arguments": {"url": "https://example.com/contact"}},
    )
    fake.add_event("tool_call", {"tool": "browser_click", "arguments": {"element": "Send"}})
    with SessionLocal() as db:
        run = db.query(QaRun).order_by(QaRun.created_at.desc()).first()
        run_id = run.id
        qa_run_service.QaRunService.sync(db, run_id)
    expect(panel).to_contain_text("Clicking 'Send'")
    expect(panel.locator(".qa-address")).to_contain_text("example.com/contact")

    fake.status = "waiting_approval"
    fake.approvals = [
        {
            "id": "budget-request",
            "run_id": fake.run_id,
            "action": "request_budget_extension",
            "status": "pending",
            "payload": {
                "arguments": {
                    "budget_usd": 2,
                    "max_turns": 120,
                    "reason": "More internal pages remain.",
                }
            },
        }
    ]
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    expect(page.get_by_text("More internal pages remain.", exact=True)).to_be_visible(timeout=15000)
    if page.viewport_size["width"] < 700:
        panel.get_by_role("button", name="Close computer", exact=True).click()
    page.get_by_role("button", name="Extend and continue", exact=True).click()
    expect(page.get_by_text("You extended the limits.", exact=True)).to_be_visible()

    fake.add_event(
        "qa_coverage",
        {
            "pages": [
                {
                    "url": "https://example.com/contact",
                    "status": "tested",
                    "reason": "Validation checked",
                },
                {
                    "url": "https://example.com/admin",
                    "status": "blocked",
                    "reason": "Login declined",
                },
            ]
        },
    )

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
        qa_run_service.QaRunService.sync(db, run_id)
    expect(page.locator(".qa-report").last).to_contain_text("1 failed", timeout=15000)
    expect(page.locator(".qa-report").last).to_contain_text("Empty email rejected")
    report = page.locator(".qa-report").last
    expect(report).to_contain_text("Partial coverage")
    report.get_by_text("Page coverage (2)", exact=True).click()
    expect(report).to_contain_text("Tested: https://example.com/contact")
    expect(report).to_contain_text("Login declined")
    # Task cards keep implementation details out of the user flow. Operator settings are separate.
    expect(report).not_to_contain_text("swarm")
    expect(panel).not_to_contain_text("swarm")
