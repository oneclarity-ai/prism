"""Dashboard history and deep links on the scratch schema with synthetic integrations."""

import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import Page, expect

from tests.e2e.test_prism_skills import create_prism


def workspace_fakes(page):
    page.route(
        "**/api/v2/qa/status",
        lambda route: route.fulfill(json={"computers": True, "available": True}),
    )
    page.route(
        "**/api/v2/operations/overview",
        lambda route: route.fulfill(
            json={
                key: []
                for key in ("agents", "positions", "tasks", "runs", "approvals", "bugs", "targets")
            }
        ),
    )
    page.route("**/api/v2/operations/secrets", lambda route: route.fulfill(json=[]))
    page.route(
        "**/api/v2/operations/analytics?*",
        lambda route: route.fulfill(
            json={"totals": {}, "by_agent": [], "by_model": [], "by_day": []}
        ),
    )
    page.route("**/api/v2/work/approvals?*", lambda route: route.fulfill(json=[]))


def test_page_urls_refresh_and_history(page: Page):
    workspace_fakes(page)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("/workspace")
    expect(page).to_have_url(re.compile(r"/workspace$"))
    expect(page.locator("#app")).to_have_attribute("data-view", "operations")
    for key, path in (
        ("tasks", "tasks"),
        ("runs", "runs"),
        ("approvals", "approvals"),
        ("bugs", "bugs"),
        ("agents", "prisms"),
        ("positions", "organization"),
        ("targets", "target-apps"),
        ("secrets", "secrets"),
        ("brain", "brain"),
        ("skills", "skills"),
        ("usage", "run-analytics"),
    ):
        page.evaluate(
            "page => document.dispatchEvent(new CustomEvent('prism:workspace-navigate', {detail: {page}}))",
            key,
        )
        expect(page).to_have_url(re.compile(f"/{path}$"))
    page.reload()
    expect(page.locator("#app")).to_have_attribute("data-view", "operations")
    expect(page.locator("#page-title")).to_have_text("Run analytics")
    page.evaluate("window.prism.setActiveTab('spending')")
    expect(page).to_have_url(re.compile(r"/spending$"))
    page.go_back()
    expect(page).to_have_url(re.compile(r"/run-analytics$"))
    expect(page.locator("#page-title")).to_have_text("Run analytics")
    page.go_forward()
    expect(page.locator("#app")).to_have_attribute("data-view", "spending")
    page.reload()
    expect(page.locator("#app")).to_have_attribute("data-view", "spending")
    assert not errors, errors


def test_prism_codes_draft_active_rename_and_direct_links(page: Page):
    draft = create_prism(page, "Onboarding colleague", activate=False)
    assert re.fullmatch(r"p[A-Za-z0-9]{5}", draft["code"])
    assert all(re.search(pattern, draft["code"][1:]) for pattern in (r"[A-Z]", r"[a-z]", r"[0-9]"))
    page.goto(f"/prisms/{draft['code']}")
    expect(page.locator("#prism-conversation-code")).to_have_text(draft["code"])
    expect(page.locator("#prism-conversation-title")).to_have_text(draft["name"])
    fresh = page.request.get(f"/api/v2/prisms/{draft['id']}").json()
    renamed = page.request.patch(
        f"/api/v2/prisms/{draft['id']}",
        data={
            "expected_lifecycle_version": fresh["lifecycle_version"],
            "name": "Renamed colleague",
        },
    )
    assert renamed.status == 200 and renamed.json()["code"] == draft["code"]
    page.reload()
    expect(page.locator("#prism-conversation-title")).to_have_text("Renamed colleague")
    expect(page.locator("#prism-conversation-code")).to_have_text(draft["code"])
    first = create_prism(page, "First active colleague")
    second = create_prism(page, "Second active colleague")
    assert len({draft["code"], first["code"], second["code"]}) == 3
    page.goto(f"/prisms/{first['code']}")
    expect(page.locator("#agent-thread-code")).to_have_text(first["code"])
    page.evaluate(
        "id => document.dispatchEvent(new CustomEvent('prism:search-result', {detail: {prismId: id}}))",
        second["id"],
    )
    expect(page).to_have_url(re.compile(f"/prisms/{second['code']}$"))
    expect(page.locator("#agent-thread-title")).to_have_text(second["name"])
    page.go_back()
    expect(page.locator("#agent-thread-title")).to_have_text(first["name"])
    expect(page.locator("#agent-thread-code")).to_have_text(first["code"])
    linked = page.context.new_page()
    linked.goto(f"/prisms/{first['code']}")
    expect(linked.locator("#agent-thread-title")).to_have_text(first["name"])
    linked.close()


def test_prism_settings_and_modal_subroutes_preserve_draft(page: Page):
    workspace_fakes(page)
    prism = create_prism(page)
    page.goto(f"/prisms/{prism['code']}/settings/skills")
    expect(page.get_by_role("tab", name="Skills", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.get_by_role("tab", name="Tools").click()
    expect(page).to_have_url(re.compile(f"/prisms/{prism['code']}/settings/tools$"))
    page.reload()
    expect(page.get_by_role("tab", name="Tools")).to_have_attribute("aria-selected", "true")
    page.go_back()
    expect(page.get_by_role("tab", name="Skills", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.goto(f"/prisms/{prism['code']}")
    page.locator("#agent-message-input").fill("Keep this unsent draft")
    page.evaluate("window.prism.openSettings('preferences')")
    expect(page).to_have_url(re.compile(r"/settings/preferences$"))
    page.locator("#settings-dialog").get_by_role("tab", name="Connections", exact=True).click()
    expect(page).to_have_url(re.compile(r"/settings/connections$"))
    page.go_back()
    expect(page.locator("#settings-dialog")).to_be_visible()
    expect(page.locator("[data-subtab-target='preferences']")).to_have_attribute(
        "aria-selected", "true"
    )
    page.keyboard.press("Escape")
    expect(page).to_have_url(re.compile(f"/prisms/{prism['code']}$"))
    expect(page.locator("#agent-message-input")).to_have_value("Keep this unsent draft")
    page.goto("/settings/connections")
    expect(page.locator("#settings-dialog")).to_be_visible()
    expect(page.locator("[data-subtab-target='connections']")).to_have_attribute(
        "aria-selected", "true"
    )


def test_missing_prism_does_not_open_cached_other_prism(page: Page):
    prism = create_prism(page)
    page.goto(f"/prisms/{prism['code']}")
    expect(page.locator("#agent-thread-title")).to_have_text(prism["name"])
    page.goto("/prisms/PR-999999999")
    expect(page.locator("#route-error-panel")).to_contain_text("could not be found")
    expect(page.locator("#agent-chat")).not_to_be_visible()
    page.go_back()
    expect(page.locator("#agent-thread-title")).to_have_text(prism["name"])


def test_run_detail_has_a_refreshable_subroute(page: Page):
    workspace_fakes(page)
    run_id = str(uuid.uuid4())
    page.route(
        f"**/api/v2/operations/runs/{run_id}",
        lambda route: route.fulfill(
            json={
                "run": {
                    "id": run_id,
                    "task_title": "Synthetic research run",
                    "status": "succeeded",
                },
                "events": [],
                "artifacts": [],
            }
        ),
    )
    page.goto(f"/runs/{run_id}")
    expect(page.locator("#operations-content")).to_contain_text("Synthetic research run")
    page.reload()
    expect(page.locator("#operations-content")).to_contain_text("Synthetic research run")
    page.get_by_role("button", name="← Back to runs").click()
    expect(page).to_have_url(re.compile(r"/runs$"))


def test_legacy_thread_link_does_not_open_cached_prism(page: Page):
    # Let startup finish creating the legacy conversation before the test requests it.
    expect(page.locator("#agent-timeline .agent-welcome")).to_be_visible()
    thread = page.request.get("/api/v2/agent/conversation").json()
    prism = create_prism(page)
    page.goto(f"/prisms/{prism['code']}")
    expect(page.locator("#agent-thread-code")).to_have_text(prism["code"])
    page.goto(f"/dashboard/?thread={thread['id']}")
    expect(page).to_have_url(re.compile(r"/assistant(?:\?|$)"))
    expect(page.locator("#agent-thread-code")).not_to_be_visible()
    expect(page.locator("#agent-chat")).to_be_visible()
    expect(page.locator("#agent-thread-title")).not_to_have_text(prism["name"])


def test_deep_links_respect_disabled_feature_flags(page: Page):
    page.route("**/api/v2/qa/status", lambda route: route.fulfill(json={"computers": False}))
    page.goto("/runs")
    expect(page.locator("#route-error-panel")).to_contain_text("computers are disabled")
    page.goto("/spending")
    expect(page.locator("#app")).to_have_attribute("data-view", "spending")
    page.route(
        "**/api/v2/prisms/foundation",
        lambda route: route.fulfill(status=404, json={"detail": "Disabled"}),
    )
    page.goto("/prisms/PR-1")
    expect(page.locator("#route-error-panel")).to_contain_text("feature is disabled")


def test_old_codes_and_uuids_open_the_new_case_sensitive_code(page: Page):
    from app.db.session import SessionLocal
    from app.models.prism_v22 import Prism

    prism = create_prism(page)
    with SessionLocal() as db:
        legacy = db.get(Prism, uuid.UUID(prism["id"])).legacy_code
    for key in (legacy, legacy.lower()):
        response = page.request.get(f"/api/v2/prisms/by-code/{key}")
        assert response.status == 200 and response.json()["code"] == prism["code"]
    wrong_case = prism["code"][:1] + prism["code"][1:].swapcase()
    assert page.request.get(f"/api/v2/prisms/by-code/{wrong_case}").status == 404
    for key in (legacy, prism["id"]):
        page.goto(f"/prisms/{key}")
        expect(page).to_have_url(re.compile(f"/prisms/{prism['code']}$"))
        expect(page.locator("#agent-thread-code")).to_have_text(prism["code"])


def test_random_codes_are_unique_during_concurrent_creation(e2e_app):
    from app.db.session import SessionLocal
    from app.models.prism_v22 import Prism

    def create(index):
        name = f"Concurrent {index} {uuid.uuid4().hex}"
        with SessionLocal() as db:
            prism = Prism(
                name=name,
                normalized_name=name.lower(),
                description="Synthetic",
                template_key="blank",
            )
            db.add(prism)
            db.commit()
            return prism.code, prism.legacy_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(create, range(40)))
    assert len({code for code, _ in created}) == 40
    assert len({alias for _, alias in created}) == 40
    for code, _ in created:
        assert re.fullmatch(r"p[A-Za-z0-9]{5}", code)
        assert all(re.search(pattern, code[1:]) for pattern in (r"[A-Z]", r"[a-z]", r"[0-9]"))
