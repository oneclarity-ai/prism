"""Synthetic visual matrix and keyboard checks for the shared dashboard system."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, expect


def capture(page: Page, name: str) -> None:
    destination = os.getenv("PRISM_DESIGN_CAPTURES")
    if destination:
        page.screenshot(path=Path(destination) / f"{name}.png", animations="disabled")


def assert_viewport(page: Page) -> None:
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    overflow = page.evaluate("""() => [...document.querySelectorAll('.workspace, .sidebar, .page, #operations-content, #agent-timeline')]
      .filter(node => node.getClientRects().length && node.clientWidth && node.scrollWidth > node.clientWidth + 1)
      .map(node => ({ name: node.id || node.className, width: node.clientWidth, scroll: node.scrollWidth }))""")
    assert overflow == []


def test_keyboard_theme_menu_persistence_and_system_preference(page: Page) -> None:
    page.emulate_media(color_scheme="dark", reduced_motion="reduce")
    page.evaluate("window.prismTheme.set('system')")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    trigger = page.locator("#profile-menu-trigger")
    trigger.focus()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("menuitem", name="Settings", exact=True)).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("radio", name="System", exact=True)).to_be_focused()
    bounds = page.locator(".profile-theme-options").bounding_box()
    assert bounds and bounds["x"] >= 0
    assert bounds["x"] + bounds["width"] <= page.viewport_size["width"]
    capture(page, f"keyboard-menu-{page.viewport_size['width']}")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    expect(page.get_by_role("radio", name="Light", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "light"
    page.evaluate("window.prismTheme.set('system')")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.emulate_media(color_scheme="light")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    trigger.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    expect(page.locator("#profile-menu")).to_be_hidden()
    trigger.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    capture(page, f"keyboard-menu-light-{page.viewport_size['width']}")
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()


def test_visual_matrix_and_keyboard_approval_with_evidence(page: Page, e2e_app) -> None:
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    base_width = page.viewport_size["width"]
    widths = [1440, 900, 720] if base_width > 700 else [390, 320]
    page.locator("#agent-message-input").fill("Draft separate Teams messages to Parv and Meera.")
    page.locator("#agent-send-button").click()
    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    cards.first.locator(".draft-more > summary").click()
    cards.first.locator("details.evidence > summary").click()
    expect(cards.first.locator("blockquote").first).to_be_visible()
    page.locator("#agent-message-input").fill("Keep this unsent draft while switching themes")

    for width in widths:
        page.set_viewport_size({"width": width, "height": 960 if width > 700 else 844})
        for theme in ("dark", "light"):
            page.evaluate("theme => window.prismTheme.set(theme)", theme)
            expect(page.locator("#agent-message-input")).to_have_value(
                "Keep this unsent draft while switching themes"
            )
            cards.first.scroll_into_view_if_needed()
            capture(page, f"approval-{theme}-{width}")
            assert_viewport(page)
            page.evaluate("window.prism.openSettings('preferences')")
            capture(page, f"settings-{theme}-{width}")
            assert_viewport(page)
            page.evaluate("window.prism.closeSettings()")
            page.locator("#profile-menu-trigger").press("ArrowDown")
            page.keyboard.press("ArrowDown")
            capture(page, f"menu-{theme}-{width}")
            page.keyboard.press("Escape")
            page.keyboard.press("Escape")
            page.evaluate("window.prism.setActiveTab('overview')")
            capture(page, f"overview-{theme}-{width}")
            assert_viewport(page)
            page.evaluate("window.prism.setActiveTab('agent')")

    # Navigate an actual native confirmation dialog using the keyboard; no real sends occur.
    reject = cards.last.get_by_role("button", name="Reject", exact=True)
    reject.focus()
    page.keyboard.press("Enter")
    dialog = page.locator("#confirm-dialog")
    expect(dialog).to_be_visible()
    capture(page, f"dialog-{base_width}")
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(reject).to_be_focused()
    assert e2e_app.graph.sent == []
    destination = cards.first.locator(".draft-dest strong").inner_text()
    approved_text = cards.first.locator("textarea.draft-body").input_value()
    cards.first.get_by_role("button", name="Approve and send").focus()
    page.keyboard.press("Enter")
    expect(cards.first.locator(".draft-state")).to_have_text("Sent")
    chat_id = "chat-parv" if destination == "Parv Pareek" else "chat-meera"
    assert e2e_app.graph.sent == [(chat_id, approved_text)]
    assert errors == []


def test_workspace_surfaces_and_semantic_contrast(page: Page) -> None:
    now = datetime.now(timezone.utc).isoformat()
    page.route(
        "**/api/v2/qa/status",
        lambda route: route.fulfill(json={"available": True, "computers": True, "reason": ""}),
    )
    page.route(
        "**/api/v2/operations/overview",
        lambda route: route.fulfill(
            json={
                "agents": [{"id": "synthetic-agent", "name": "Research Prism", "status": "active"}],
                "tasks": [
                    {
                        "id": "synthetic-task",
                        "title": "Review release readiness",
                        "goal": "Check the release with evidence",
                        "agent_id": "synthetic-agent",
                        "status": "todo",
                        "created_at": now,
                    }
                ],
                "runs": [
                    {
                        "id": "synthetic-run",
                        "task_title": "Review release readiness",
                        "agent_id": "synthetic-agent",
                        "status": "succeeded",
                        "created_at": now,
                        "started_at": now,
                        "ended_at": now,
                        "total_tokens": 1200,
                        "cost_usd": 0.03,
                    }
                ],
                "targets": [],
                "approvals": [],
                "bugs": [],
                "positions": [],
            }
        ),
    )
    page.route("**/api/v2/operations/secrets", lambda route: route.fulfill(json=[]))
    page.route("**/api/v2/work/approvals?**", lambda route: route.fulfill(json=[]))
    page.route(
        "**/api/v2/operations/analytics?**",
        lambda route: route.fulfill(
            json={"totals": {}, "by_day": [], "by_agent": [], "by_model": []}
        ),
    )
    page.reload()
    expect(page.locator("#sidebar-workspace-tab")).to_be_visible()
    page.evaluate("window.prism.setSidebarSection('workspace')")
    # The desktop invocation also covers the tablet breakpoint.
    widths = [1440, 900, 720] if page.viewport_size["width"] > 700 else [390, 320]
    for width in widths:
        page.set_viewport_size({"width": width, "height": 960 if width > 700 else 844})
        for theme in ("dark", "light"):
            page.evaluate("theme => window.prismTheme.set(theme)", theme)
            for target in (
                "overview",
                "tasks",
                "runs",
                "approvals",
                "bugs",
                "agents",
                "positions",
                "targets",
                "secrets",
                "usage",
            ):
                page.locator(f"[data-workspace-page='{target}']").evaluate(
                    "button => button.click()"
                )
                expect(page.locator(".workspace-loading")).to_have_count(0)
                expect(page.locator("#operations-content")).not_to_contain_text(
                    "Workspace could not load"
                )
                assert_viewport(page)
                if target in ("runs", "overview", "approvals"):
                    capture(page, f"workspace-{target}-{theme}-{width}")

            failures = page.evaluate("""() => {
              const css = getComputedStyle(document.documentElement);
              const rgb = name => {
                const hex = css.getPropertyValue(name).trim();
                return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
              };
              const lum = values => values.map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
                .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
              const failures = [];
              for (const surface of ['--ds-workspace', '--ds-panel', '--ds-selected', '--ds-inset']) {
                for (const ink of ['--ds-ink', '--ds-secondary', '--ds-muted', '--ds-success', '--ds-warning', '--ds-error', '--ds-link', '--ds-focus']) {
                  const a = lum(rgb(ink)), b = lum(rgb(surface));
                  const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
                  if (ratio < (ink === '--ds-focus' ? 3 : 4.5)) failures.push({ ink, surface, ratio });
                }
              }
              return failures;
            }""")
            assert failures == []


def test_loading_and_unavailable_states(page: Page) -> None:
    held = []
    page.route("**/api/v2/operations/overview", lambda route: held.append(route))
    page.route(
        "**/api/v2/qa/status",
        lambda route: route.fulfill(json={"available": True, "computers": True, "reason": ""}),
    )
    page.reload()
    expect(page.locator("#sidebar-workspace-tab")).to_be_visible()
    page.evaluate("window.prism.applyV24Mode(true); window.prism.setActiveTab('operations')")
    expect(page.locator(".workspace-loading")).to_be_visible()
    expect(page.locator(".workspace-loading")).to_have_attribute("role", "status")
    capture(page, f"loading-{page.viewport_size['width']}")
    assert held
    held[0].fulfill(
        status=503,
        json={"detail": "Synthetic computer service unavailable", "code": "external_service_error"},
    )
    expect(page.locator("#operations-content")).to_contain_text("Workspace could not load")
    for theme in ("dark", "light"):
        page.evaluate("theme => window.prismTheme.set(theme)", theme)
        capture(page, f"unavailable-{theme}-{page.viewport_size['width']}")
        assert_viewport(page)


def test_failed_and_uncertain_send_states(page: Page, e2e_app, monkeypatch) -> None:
    import httpx

    from app.services.errors import ExternalServiceError

    def fail(_self, chat_id, _content, _signature=None):
        if chat_id == "chat-parv":
            raise httpx.ReadTimeout("Synthetic uncertain delivery")
        raise ExternalServiceError("Synthetic rejected delivery")

    monkeypatch.setattr(e2e_app.graph, "send_chat_message", fail)
    page.locator("#agent-message-input").fill("Draft separate Teams messages to Parv and Meera.")
    page.locator("#agent-send-button").click()
    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    for index in range(2):
        card = cards.nth(index)
        destination = card.locator(".draft-dest strong").inner_text()
        card.get_by_role("button", name="Approve and send").click()
        expect(card.locator(".draft-state")).to_have_text(
            "Needs confirmation" if destination == "Parv Pareek" else "Failed"
        )
    for theme in ("dark", "light"):
        page.evaluate("theme => window.prismTheme.set(theme)", theme)
        cards.first.scroll_into_view_if_needed()
        capture(page, f"delivery-states-{theme}-{page.viewport_size['width']}")
        assert_viewport(page)
    assert e2e_app.graph.sent == []
