"""The global theme, profile menu, and settings cost controls stay usable."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_profile_menu_theme_and_provider_spend(page: Page) -> None:
    page.route(
        "https://open.er-api.com/v6/latest/USD",
        lambda route: route.fulfill(json={"rates": {"INR": 83}}),
    )

    def usage(route):
        item = {
            "calls": 1,
            "estimated_cost_usd": "0.12",
            "unpriced_calls": 0,
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "output_tokens": 20,
        }
        periods = {
            name: {"prism": item, "swarm": {**item, "estimated_cost_usd": "0.08"}}
            for name in ("today", "week", "month", "total")
        }
        route.fulfill(
            json={
                "timezone": "Asia/Kolkata",
                "range": {"from": "2026-11-01", "to": "2026-11-21"},
                "periods": periods,
                "by_feature": {
                    "prism": [{**item, "group": "prism_work_plan"}],
                    "swarm": [
                        {**item, "estimated_cost_usd": "0.08", "group": "qa_tester_test_runs"}
                    ],
                },
                "by_model": {
                    "prism": [{**item, "group": "test-model"}],
                    "swarm": [{**item, "estimated_cost_usd": "0.08", "group": "test-model"}],
                },
                "by_provider": [
                    {**item, "group": "openai"},
                    {**item, "group": "qa_workspace", "estimated_cost_usd": "0.08"},
                ],
            }
        )

    page.route("**/api/v1/usage/llm/sources?**", usage)
    page.route(
        "**/api/v1/usage/llm/azure-billed?**",
        lambda route: route.fulfill(json={"configured": False}),
    )

    page.locator("#profile-menu-trigger").click()
    expect(page.locator("#profile-menu")).to_be_visible()
    page.locator("[data-profile-theme='dark']").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    page.locator("#profile-menu-trigger").click()
    page.locator("[data-profile-action='settings']").click()
    page.locator("[data-subtab-target='general']").click()
    expect(page.locator("[data-subtab='general']")).to_be_visible()
    page.locator("[data-settings-link='spending']").click()
    expect(page.locator("[data-tab='spending']")).to_be_visible()
    page.locator("[data-tab='spending'] [data-currency='USD']").click()
    expect(page.locator("#settings-cost-total")).to_contain_text("$0.2000", timeout=15000)
    expect(page.locator("#settings-provider-costs")).to_contain_text("OpenAI")
    expect(page.locator("#settings-provider-costs")).to_contain_text("Agentic swarm")

    page.locator("#profile-menu-trigger").click()
    page.locator("[data-profile-theme='light']").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")

    page.evaluate("window.prism.openSettings('account')")
    expect(page.locator("[data-subtab='account']")).to_be_visible()
    page.get_by_role("button", name="Close settings").click()
    page.locator("#profile-menu-trigger").click()
    page.get_by_role("menuitem", name="System status").click()
    expect(page.locator("#profile-status-details")).to_be_visible()
