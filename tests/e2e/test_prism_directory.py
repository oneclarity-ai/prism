"""Browser journeys for the private messenger-style Prism workspace."""

from playwright.sync_api import Page, expect


def open_sidebar_if_narrow(page: Page) -> None:
    if page.viewport_size and page.viewport_size["width"] < 700:
        page.get_by_role("button", name="Open sidebar").click()


def complete_onboarding(page: Page) -> None:
    page.get_by_role("button", name="Let’s get started").click()
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
    dialog.get_by_role("button", name="Create draft").click()
    if page.viewport_size and page.viewport_size["width"] < 700:
        page.get_by_role("button", name="Close sidebar").click()

    expect(page.locator("#prism-conversation-title")).to_have_text("Executive Updates")
    complete_onboarding(page)
    expect(page.locator("#prism-onboarding-stream")).to_contain_text("Working agreement")
    expect(page.locator(".working-agreement")).to_contain_text("All accessible Teams chats")
    expect(page.locator(".working-agreement")).to_contain_text(
        "Nothing is sent without your explicit approval"
    )
    page.get_by_role("button", name="Confirm and activate").click()
    expect(page.locator("#prism-conversation-state")).to_contain_text("active")
    # Once active, the Prism's own conversation uses the standard composer.
    expect(page.locator("#agent-message-input")).to_be_visible()
    page.get_by_role("button", name="Preferences").click()
    page.locator("#agent-preference-input").fill("Use concise bullet points.")
    page.locator("#agent-preference-form").get_by_role("button", name="Remember").click()
    expect(page.locator("#agent-preference-list")).to_contain_text("Use concise bullet points.")

    page.reload()
    open_sidebar_if_narrow(page)
    page.get_by_role("button", name="Executive Updates").click()
    expect(page.locator("#prism-conversation-state")).to_contain_text("active")
    expect(page.locator("#agent-message-input")).to_be_visible()
    page.get_by_role("button", name="Preferences").click()
    expect(page.locator("#agent-preference-list")).to_contain_text("Use concise bullet points.")
    page.get_by_role("button", name="Close preferences").click()
