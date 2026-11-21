"""Browser journeys for the private messenger-style Prism workspace."""

from playwright.sync_api import Page, expect


def open_sidebar_if_narrow(page: Page) -> None:
    if page.viewport_size and page.viewport_size["width"] < 700:
        page.locator("#sidebar-open:visible, .chat-sidebar-open:visible").first.click()


def complete_onboarding(page: Page) -> None:
    expect(page.locator(".onboarding-choices, #prism-onboarding-custom-wrap")).not_to_have_count(0)
    page.locator("#prism-onboarding-custom").fill("Give me a clear view of important work.")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("Production incidents")).to_be_visible()
    page.get_by_label("Production incidents").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("Only when I ask")).to_be_visible()
    page.get_by_label("Only when I ask").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("All accessible Teams chats")).to_be_visible()
    page.get_by_label("All accessible Teams chats").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("Friendly and assistant-like")).to_be_visible()
    page.get_by_label("Friendly and assistant-like").check()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_label("Recommendations only")).to_be_visible()
    page.get_by_label("Recommendations only").check()
    page.get_by_role("button", name="Continue").click()
    page.locator("#prism-onboarding-skip").click()


def test_create_activate_and_resume_a_private_prism_conversation(page: Page) -> None:
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name="Create Prism").click()
    dialog = page.locator("#prism-editor-dialog")
    dialog.get_by_label("Name").fill("Executive Updates")
    dialog.get_by_label("What is this Prism responsible for?").fill(
        "Keep me informed about important Teams work in a friendly tone."
    )
    dialog.get_by_label("Green").check()
    dialog.get_by_role("button", name="Create prism").click()
    if page.viewport_size and page.viewport_size["width"] < 700:
        page.get_by_role("button", name="Close sidebar").click()

    expect(page.locator("#prism-conversation-title")).to_contain_text("Executive Updates")
    # The chosen colour follows the Prism into the sidebar and its chat header.
    expect(page.locator(".prism-nav-item .nav-logo")).to_have_attribute("data-color", "green")
    expect(page.locator("#prism-conversation-logo .prism-logo")).to_have_attribute(
        "data-color", "green"
    )
    complete_onboarding(page)
    expect(page.locator("#prism-onboarding-stream")).to_contain_text("My job:")
    expect(page.locator(".working-agreement")).to_contain_text("All accessible Teams chats")
    expect(page.locator(".working-agreement")).to_contain_text(
        "Nothing is sent without your explicit approval"
    )
    page.get_by_role("button", name="Confirm and activate").click()
    expect(page.locator("#prism-conversation-state")).to_contain_text("active")
    # The chat answers create three skills; there is no second questionnaire.
    expect(page.locator("#prism-skill-setup")).to_have_count(0)
    expect(page.locator("#agent-timeline")).to_contain_text("I created 3 skills")
    # Once active, the Prism's own conversation uses the standard composer.
    expect(page.locator("#agent-message-input")).to_be_visible()
    page.get_by_role("button", name="Preferences").click()
    expect(page.locator("#agent-preferences-intro")).to_contain_text("Executive Updates only")
    page.locator("#agent-preference-input").fill("Use concise bullet points.")
    page.locator("#agent-preference-form").get_by_role("button", name="Add", exact=True).click()
    expect(page.locator("#agent-preference-list")).to_contain_text("Use concise bullet points.")

    page.reload()
    expect(page.locator("#agent-thread-title")).to_have_text("Executive Updates")
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name="Executive Updates").click()
    expect(page.locator("#prism-conversation-state")).to_contain_text("active")
    expect(page.locator("#agent-message-input")).to_be_visible()
    page.get_by_role("button", name="Preferences").click()
    expect(page.locator("#agent-preference-list")).to_contain_text("Use concise bullet points.")
    page.get_by_role("button", name="Close settings").click()


def test_browser_tab_title_follows_the_open_prism(page: Page) -> None:
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name="Create Prism").click()
    dialog = page.locator("#prism-editor-dialog")
    dialog.get_by_label("Name").fill("Tab Tester")
    dialog.get_by_label("What is this Prism responsible for?").fill("Checks the tab title.")
    dialog.get_by_label("Pink").check()
    dialog.get_by_role("button", name="Create prism").click()
    expect(page).to_have_title("Tab Tester · Prism")
    # The tab icon stays the static brand logo whichever Prism is open.
    icon = page.locator("link[rel='icon']")
    assert "data:image/svg+xml" in icon.get_attribute("href")
    brand_icon = icon.get_attribute("href")
    # Chats retains the selected Prism; a different page uses its own title and the brand icon.
    page.evaluate("window.prism.setActiveTab('spending')")
    expect(page).to_have_title("Spending · Prism")
    assert icon.get_attribute("href") == brand_icon
