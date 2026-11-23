"""Regenerate the README screenshots from the deterministic fakes (synthetic data only).

    E2E_SCREENSHOTS=1 RUN_E2E=1 .venv/bin/pytest tests/e2e/test_docs_screenshots.py

Images go to the repository-level docs/screenshots directory with a `v3-` prefix.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.skipif(
    os.getenv("E2E_SCREENSHOTS") != "1", reason="Set E2E_SCREENSHOTS=1 to regenerate screenshots"
)

OUTPUT = Path(__file__).resolve().parents[4] / "docs" / "screenshots"
HIDE = "*{caret-color:transparent!important}.setup-callout{display:none!important}"


def shot(page: Page, name: str, kind: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.mouse.move(900, 500)
    page.wait_for_timeout(400)
    page.screenshot(path=OUTPUT / f"v3-{name}-{kind}.png", animations="disabled")


def test_dashboard_screens(page: Page) -> None:
    kind = "desktop" if page.viewport_size["width"] > 640 else "narrow"
    desktop = kind == "desktop"
    page.add_style_tag(content=HIDE)
    page.emulate_media(color_scheme="light", reduced_motion="reduce")
    page.evaluate("window.prismTheme.set('light')")

    # 1. Chat: ask for what needs attention, with disclosed sources.
    page.locator("#agent-message-input").fill("What needs my attention across the release team?")
    page.locator("#agent-send-button").click()
    turn = page.locator(".turn.assistant", has_text="release schema")
    expect(turn).to_be_visible()
    summary = turn.locator("details.source-plan > summary")
    if summary.first.is_visible():
        summary.first.click()
    shot(page, "chat-attention", kind)

    # 2. Approval cards for coordinated drafts.
    page.locator("#agent-message-input").fill("Draft separate Teams messages to Parv and Meera.")
    page.locator("#agent-send-button").click()
    expect(page.locator(".planned-action .draft-card")).to_have_count(2)
    page.locator(".action-plan").scroll_into_view_if_needed()
    shot(page, "approval-cards", kind)

    # 3. The same chat in the dark theme.
    page.evaluate("window.prismTheme.set('dark')")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    shot(page, "chat-dark", kind)
    page.evaluate("window.prismTheme.set('light')")

    if not desktop:
        return

    # 4. Create a Prism.
    page.get_by_role("button", name="Create Prism").click()
    expect(page.locator("#prism-editor-dialog")).to_be_visible()
    shot(page, "create-prism", kind)
    page.keyboard.press("Escape")

    # 5. Universal search.
    page.evaluate("window.prism.openSearch()")
    expect(page.locator("#search-dialog")).to_be_visible()
    shot(page, "search", kind)
    page.keyboard.press("Escape")

    # 6. Settings: AI provider.
    page.evaluate("window.prism.openSettings('provider')")
    expect(page.locator("#settings-dialog")).to_be_visible()
    shot(page, "settings-provider", kind)
    page.keyboard.press("Escape")
