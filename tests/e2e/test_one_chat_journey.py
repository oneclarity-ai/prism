"""Phase 13 release journey, driven through the browser at desktop and phone widths."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def ask(page: Page, text: str) -> None:
    box = page.locator("#agent-message-input")
    box.fill(text)
    page.locator("#agent-send-button").click()


def test_manager_asks_without_choosing_a_chat_and_sees_disclosed_sources(page: Page) -> None:
    expect(page.locator("#agent-source-chip-label")).to_have_text("All chats")
    # No person or group appears as a Prism chat anywhere in primary navigation.
    assert page.locator(".thread-item").count() == 0

    ask(page, "What needs my attention across the release team this morning?")

    turn = page.locator(".turn.assistant", has_text="The release schema is the open dependency.")
    expect(turn).to_be_visible()
    turn.locator(".turn-details > summary").click()
    chips = turn.locator(".source-chips")
    expect(chips).to_contain_text("Read from")
    expect(chips).to_contain_text("Auto-selected")
    assert chips.locator(".tag.blue").count() >= 2
    # Evidence is expandable, grouped by source, and rendered as text.
    turn.locator("details.evidence > summary").first.click()
    expect(turn.locator("details.evidence blockquote").first).to_be_visible()
    expect(turn.get_by_text("Why these sources")).to_be_visible()
    assert page.locator("#agent-timeline [data-message]").count() == 1


def test_two_coordinated_replies_are_edited_then_one_approved_and_one_rejected(
    page: Page, e2e_app
) -> None:
    chat_ids = {"Parv Pareek": "chat-parv", "Meera Shah": "chat-meera"}
    ask(page, "Draft separate Teams messages to Parv and Meera.")

    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    expect(page.locator(".action-plan")).to_contain_text("ready for you to check")

    # Card order follows the plan, so read each destination instead of assuming one.
    approved_to = cards.nth(0).locator(".draft-dest strong").inner_text()
    rejected_to = cards.nth(1).locator(".draft-dest strong").inner_text()
    assert {approved_to, rejected_to} == set(chat_ids)
    approved_text = f"{approved_to.split()[0]}, please publish the schema by 1:00 PM."
    rejected_text = f"{rejected_to.split()[0]}, continue with unaffected work."

    cards.nth(0).locator("textarea.draft-body").fill(approved_text)
    cards.nth(1).locator("textarea.draft-body").fill(rejected_text)
    # An unsaved edit cannot be approved: approval must cover exactly the text on screen.
    expect(cards.nth(0).get_by_role("button", name="Approve and send")).to_be_disabled()
    cards.nth(0).get_by_role("button", name="Save edit").click()
    expect(cards.nth(0).locator("textarea.draft-body")).to_have_value(approved_text)
    cards.nth(1).get_by_role("button", name="Save edit").click()
    expect(cards.nth(1).locator("textarea.draft-body")).to_have_value(rejected_text)

    cards.nth(0).get_by_role("button", name="Approve and send").click()
    expect(cards.nth(0)).to_contain_text("Sent")
    # Approving one card never approves the other.
    expect(cards.nth(1)).to_contain_text("Awaiting approval")
    assert e2e_app.graph.sent == [(chat_ids[approved_to], approved_text)]

    cards.nth(1).get_by_role("button", name="Reject").click()
    page.locator("#confirm-ok").click()
    expect(cards.nth(1)).to_contain_text("Rejected")
    assert len(e2e_app.graph.sent) == 1

    # The decisions, edits, and delivery survive a refresh without re-sending anything.
    page.reload()
    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("Sent")
    expect(cards.nth(1)).to_contain_text("Rejected")
    page.locator(".turn-details > summary").first.click()
    audit = page.locator("details.audit").first
    audit.locator("summary").click()
    expect(audit).to_contain_text("Delivered to Teams")
    expect(audit).to_contain_text("Edited by you")
    assert len(e2e_app.graph.sent) == 1
