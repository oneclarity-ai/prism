"""Capture README screenshots from a RUNNING Prism (real product, real data).

    PRISM_OPERATOR_TOKEN=... apps/prism/.venv/bin/python scripts/capture_screenshots.py

The token is read from the environment and written nowhere. Output goes to docs/screenshots/.
Review every image before committing: it shows whatever your instance contains. This script
deliberately avoids the Chief of Staff chat (Teams content) and the Account/Connections settings
(your email), and hides the profile name in the sidebar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.getenv("PRISM_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("PRISM_OPERATOR_TOKEN", "")
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
# Prism codes whose chats hold work reports (override for your own instance).
REPORT_PRISMS = os.getenv("PRISM_REPORT_CODES", "p817fY,pocA9q").split(",")

HIDE = (
    "*{caret-color:transparent!important}"
    ".setup-callout{display:none!important}"
    ".prism-nav-preview{visibility:hidden!important}"
    "#profile-menu-trigger .profile-name,#profile-menu-trigger .profile-meta,"
    "#profile-menu-trigger span:not(.profile-avatar){visibility:hidden!important}"
)


def shot(page: Page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.mouse.move(1100, 880)
    page.wait_for_timeout(700)
    page.screenshot(path=OUT / f"{name}.png", animations="disabled")
    print("saved", name)


def settle(page: Page, ms: int = 1500) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def main() -> int:
    if not TOKEN:
        print("Set PRISM_OPERATOR_TOKEN in the environment.", file=sys.stderr)
        return 2
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for theme in ("light", "dark"):
            ctx = browser.new_context(
                base_url=BASE, viewport={"width": 1440, "height": 900}, color_scheme=theme
            )
            ctx.add_init_script(
                f"localStorage.setItem('manager-agent-operator-token', {TOKEN!r});"
                f"localStorage.setItem('manager-agent-theme', {theme!r});"
            )
            page = ctx.new_page()
            suffix = "" if theme == "light" else "-dark"
            page.goto("/dashboard/")
            page.add_style_tag(content=HIDE)
            settle(page, 2500)

            if theme == "light":
                # Prism list and a work report in a chat.
                for code in REPORT_PRISMS:
                    page.goto(f"/prisms/{code}")
                    page.add_style_tag(content=HIDE)
                    settle(page, 2500)
                    page.evaluate(
                        "(() => { const t = document.querySelector('#agent-timeline'); "
                        "if (t) t.scrollTop = t.scrollHeight; })()"
                    )
                    shot(page, f"chat-{code}")

                # Workspace pages.
                page.goto("/dashboard/")
                page.add_style_tag(content=HIDE)
                settle(page)
                page.evaluate("window.prism.setSidebarSection('workspace')")
                for key, name in (
                    ("agents", "workspace-prisms"),
                    ("runs", "workspace-runs"),
                    ("tasks", "workspace-tasks"),
                    ("approvals", "workspace-approvals"),
                ):
                    nav = page.locator(f"[data-workspace-page='{key}']:visible")
                    if nav.count():
                        nav.first.click()
                        settle(page, 1800)
                        shot(page, name)
                page.goto("/spending")
                page.add_style_tag(content=HIDE)
                settle(page, 2000)
                shot(page, "workspace-spending")

                # Dialogs.
                page.goto("/dashboard/")
                page.add_style_tag(content=HIDE)
                settle(page)
                page.evaluate("window.prism.openSettings('provider')")
                settle(page, 1800)
                shot(page, "settings-provider")
                page.keyboard.press("Escape")
                page.evaluate("window.prism.openSearch()")
                page.keyboard.type("research")
                settle(page, 1200)
                shot(page, "search")
                page.keyboard.press("Escape")
            else:
                page.goto(f"/prisms/{REPORT_PRISMS[0]}")
                page.add_style_tag(content=HIDE)
                settle(page, 2500)
                page.evaluate(
                    "(() => { const t = document.querySelector('#agent-timeline'); "
                    "if (t) t.scrollTop = t.scrollHeight; })()"
                )
                shot(page, f"chat-{REPORT_PRISMS[0]}{suffix}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
