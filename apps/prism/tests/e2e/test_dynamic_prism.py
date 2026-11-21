"""v2.4 in a browser: a custom role's task, its computer panel, the secure cards and the report.

Written to run against a fake engine. Not run yet: the Playwright suite is paused until asked for.
"""

from __future__ import annotations

import re
import uuid

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.test_prism_directory import open_sidebar_if_narrow


def seed_work_prism(name: str) -> None:
    from app.db.session import SessionLocal
    from app.models.enums import PrismLifecycleState
    from app.schemas.prism_v22 import PrismCreate
    from app.services.prism_lifecycle_service import PrismLifecycleService

    with SessionLocal() as db:
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(
                name=name,
                description="Find companies and list them.",
                template_key="blank",
                capabilities=["files"],
                logins_policy="ask",
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


def test_a_custom_prism_plans_works_asks_and_reports(page: Page, e2e_app, monkeypatch) -> None:
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.models.qa import QaRun
    from app.services import qa_run_service
    from app.services.qa_swarm_client import QaSwarmClient
    from tests.test_dynamic_prism_integration import FakeEngine

    monkeypatch.setenv("PRISM_V24_ENABLED", "true")
    monkeypatch.setenv("QA_SWARM_URL", "http://swarm.invalid")
    monkeypatch.setenv("QA_SWARM_EMAIL", "tester@example.com")
    monkeypatch.setenv("QA_SWARM_PASSWORD", "secret-password")
    get_settings.cache_clear()
    engine = FakeEngine()
    monkeypatch.setattr(
        qa_run_service,
        "make_client",
        lambda: QaSwarmClient(get_settings(), transport=httpx.MockTransport(engine)),
    )
    name = f"Riya {uuid.uuid4().hex[:5]}"
    seed_work_prism(name)
    page.reload()
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name=name).first.click()

    expect(page.locator("#agent-computer-button")).to_be_visible()
    page.locator("#agent-computer-button").click()
    expect(page.locator("#qa-computer-body")).to_contain_text("Asleep")
    page.locator("#qa-computer-close").click()

    page.locator("#agent-message-input").fill(
        "find 5 fintech companies in Bangalore and list their websites"
    )
    page.locator("#agent-send-button").click()
    plan = page.locator(".qa-plan").last
    expect(plan).to_contain_text("Steps")
    expect(plan).to_contain_text("Asks you first")
    plan.get_by_role("button", name="Start", exact=True).click()

    with SessionLocal() as db:
        run = db.query(QaRun).order_by(QaRun.created_at.desc()).first()
        run_id = run.id
    engine.add_event("checklist", {"steps": [{"title": "Search", "status": "doing"}]})
    engine.add_event("artifact", {"kind": "frame", "artifact_id": "f1", "file": "f.jpeg"})
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    panel = page.locator("#qa-computer-panel")
    expect(panel).to_contain_text("Search")
    expect(panel.locator(".qa-shot")).to_have_count(1)

    # The Prism asks for a login in a secure card; the password never shows in the page afterwards.
    engine.status = "waiting_approval"
    engine.approvals.append(
        {
            "id": "ap-1",
            "run_id": engine.run_id,
            "status": "pending",
            "action": "request_login",
            "payload": {"arguments": {"site": "https://linkedin.com", "reason": "to find people"}},
        }
    )
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    card = page.locator(".qa-login").last
    expect(card).to_be_visible(timeout=15000)
    expect(panel).to_contain_text("Waiting for you")
    page.locator("#qa-computer-close").click()
    card.locator("input[type=text]").fill("bob@example.com")
    card.locator("input[type=password]").fill("hunter2-secret")
    card.get_by_role("button", name="Sign in").click()
    expect(card).not_to_be_visible(timeout=15000)
    expect(page.locator("body")).not_to_contain_text("hunter2-secret", timeout=15000)

    engine.status = "succeeded"
    engine.result = {
        "outcome": "passed",
        "results": [{"company": "Acme", "site": "acme.com"}],
        "files": [{"name": "leads.csv", "artifact_id": "file-1"}],
    }
    with SessionLocal() as db:
        qa_run_service.QaRunService.sync(db, run_id)
    report = page.locator(".qa-report").last
    expect(report).to_contain_text("1 found", timeout=15000)
    expect(report).to_contain_text("Acme")
    expect(report.get_by_role("button", name=re.compile("Download leads.csv"))).to_be_visible()
    expect(report).not_to_contain_text("swarm")
