"""Regenerate the README screenshots from the deterministic fakes: E2E_SCREENSHOTS=1 make test-e2e."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.skipif(
    os.getenv("E2E_SCREENSHOTS") != "1", reason="Set E2E_SCREENSHOTS=1 to regenerate screenshots"
)

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "screenshots"


def test_capture_one_conversation_screens(page: Page) -> None:
    width = page.viewport_size["width"]
    kind = "desktop" if width > 640 else "narrow"
    # The scratch environment has no Microsoft or model setup; hide that banner for documentation.
    page.add_style_tag(
        content="*{caret-color:transparent!important}.setup-callout{display:none!important}"
    )

    page.locator("#agent-message-input").fill("What needs my attention across the release team?")
    page.locator("#agent-send-button").click()
    turn = page.locator(".turn.assistant", has_text="release schema")
    expect(turn).to_be_visible()
    turn.locator("details.source-plan > summary").click()
    page.screenshot(path=OUTPUT / f"v2.1-attention-sources-{kind}.png")

    page.locator("#agent-message-input").fill("Draft separate Teams messages to Parv and Meera.")
    page.locator("#agent-send-button").click()
    expect(page.locator(".planned-action .draft-card")).to_have_count(2)
    page.locator(".action-plan").scroll_into_view_if_needed()
    page.screenshot(path=OUTPUT / f"v2.1-coordinated-approvals-{kind}.png")
