"""Recovery, safety, and navigation states of the one-conversation Agent workspace."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from app.services.errors import (
    ExternalPermissionError,
    ExternalThrottleError,
    ReconnectRequiredError,
)

QUESTION = "What needs my attention across the release team?"


def ask(page: Page, text: str) -> None:
    page.locator("#agent-message-input").fill(text)
    page.locator("#agent-send-button").click()


@pytest.mark.parametrize(
    ("error", "title", "has_reconnect"),
    [
        (ReconnectRequiredError("Reconnect Microsoft"), "Reconnect Microsoft to continue", True),
        (
            ExternalPermissionError("Chat access was not granted"),
            "Microsoft permission is missing",
            True,
        ),
        (
            ExternalThrottleError("Microsoft is throttling"),
            "Microsoft is asking Prism to slow down",
            False,
        ),
    ],
    ids=["reconnect", "permission", "throttled"],
)
def test_microsoft_failures_show_a_recovery_step_and_never_claim_a_send(
    page: Page, e2e_app, error, title, has_reconnect
) -> None:
    e2e_app.graph.read_error = error
    ask(page, QUESTION)

    notice = page.locator("#agent-composer-notice .callout.recovery")
    expect(notice).to_contain_text(title)
    expect(notice).to_contain_text("Nothing was sent")
    assert (notice.get_by_role("button", name="Reconnect Microsoft").count() == 1) is has_reconnect
    # The manager's question stays in the composer to retry, and nothing was sent.
    expect(page.locator("#agent-message-input")).to_have_value(QUESTION)
    assert e2e_app.graph.sent == []

    # Recovering Microsoft access and asking again clears the notice.
    e2e_app.graph.read_error = None
    page.locator("#agent-send-button").click()
    expect(page.locator(".turn.assistant", has_text="release schema")).to_be_visible()
    expect(page.locator("#agent-composer-notice .callout")).to_have_count(0)


def test_hostile_teams_and_model_text_never_becomes_markup(page: Page, e2e_app) -> None:
    e2e_app.graph.hostile = True
    ask(page, QUESTION)

    turn = page.locator(".turn.assistant", has_text="The release schema")
    expect(turn).to_be_visible()
    # The model's tags are shown literally as text, not parsed.
    expect(turn).to_contain_text("<img src=x")
    turn.locator(".turn-details > summary").click()
    turn.locator("details.evidence > summary").first.click()
    assert (
        page.locator("#agent-timeline img, #agent-timeline script, #agent-timeline b").count() == 0
    )
    assert page.evaluate("window.__xss") is None


def test_double_clicking_approve_sends_exactly_once(page: Page, e2e_app) -> None:
    ask(page, "Draft separate Teams messages to Parv and Meera.")
    card = page.locator(".planned-action .draft-card").first
    expect(card).to_be_visible()

    card.get_by_role("button", name="Approve and send").dblclick()
    expect(card).to_contain_text("Sent")
    page.reload()
    expect(page.locator(".planned-action .draft-card").first).to_contain_text("Sent")
    assert len(e2e_app.graph.sent) == 1


def test_failed_delivery_is_shown_as_failed_and_not_as_sent(page: Page, e2e_app) -> None:
    ask(page, "Draft separate Teams messages to Parv and Meera.")
    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    label = cards.first.locator(".draft-dest strong").inner_text()
    e2e_app.graph.fail_sends_for = {"chat-parv" if "Parv" in label else "chat-meera"}

    cards.first.get_by_role("button", name="Approve and send").click()
    expect(cards.first).to_contain_text("Failed")
    expect(cards.first).not_to_contain_text("Delivered from your Microsoft Teams account")
    assert e2e_app.graph.sent == []
    # The other card is untouched and still needs its own approval.
    expect(cards.nth(1)).to_contain_text("Awaiting approval")


def test_search_jumps_into_history_and_returns_to_latest(page: Page) -> None:
    ask(page, QUESTION)
    expect(page.locator(".turn.assistant", has_text="release schema")).to_be_visible()
    ask(page, "What else needs my attention across the release team this afternoon?")
    expect(page.locator(".turn.assistant")).to_have_count(2)

    page.locator("#agent-search-button").click()
    search = page.get_by_label("Search your conversation with Prism")
    expect(search).to_be_focused()
    search.fill("What needs my attention")  # only the first question; the second says "What else"
    result = page.locator(".search-result", has_text="What needs my attention")
    expect(result).to_have_count(1)
    result.click()

    expect(page.locator(".history-banner")).to_contain_text("Viewing earlier history")
    expect(page.locator("#agent-search-panel")).to_be_hidden()
    page.get_by_role("button", name="Back to latest").click()
    expect(page.locator(".history-banner")).to_have_count(0)
    expect(page.locator("#agent-message-input")).to_be_focused()


def test_auto_resolves_ambiguous_request_without_source_picker(page: Page, e2e_app) -> None:
    ask(page, "Summarize decisions and open questions across the release team")

    dialog = page.locator("#agent-source-dialog")
    expect(dialog).to_be_hidden()
    turn = page.locator(".turn.assistant", has_text="release schema")
    expect(turn).to_be_visible()
    expect(turn.locator(".source-chips")).to_contain_text("Auto-selected")
    assert e2e_app.graph.sent == []


def test_search_without_matches_says_so(page: Page) -> None:
    ask(page, QUESTION)
    expect(page.locator(".turn.assistant", has_text="release schema")).to_be_visible()
    page.locator("#agent-search-button").click()
    page.get_by_label("Search your conversation with Prism").fill("zzz-nothing-matches")
    expect(page.locator("#agent-search-results")).to_contain_text("No messages match")
    page.keyboard.press("Escape")
    expect(page.locator("#agent-search-panel")).to_be_hidden()
    expect(page.locator("#agent-search-button")).to_be_focused()


def test_workspace_has_no_horizontal_scroll_and_exposes_a_live_region(page: Page) -> None:
    ask(page, "Draft separate Teams messages to Parv and Meera.")
    expect(page.locator(".planned-action .draft-card").first).to_be_visible()

    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0
    expect(page.locator("#agent-timeline")).to_have_attribute("aria-live", "polite")
    # Status is communicated with words, not colour alone.
    expect(page.locator(".draft-card .draft-state").last).not_to_have_text("")


def test_source_filter_defaults_to_auto_and_can_limit_requests(page: Page, e2e_app) -> None:
    chip = page.locator("#agent-source-chip")
    expect(chip).to_contain_text("All chats")
    chip.click()
    dialog = page.locator("#agent-source-dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Parv Pareek").first.click()
    expect(chip).to_contain_text("Parv Pareek")

    ask(page, QUESTION)
    turn = page.locator(".turn.assistant", has_text="release schema")
    expect(turn.locator(".source-chips")).to_contain_text("You limited this to")
    assert turn.locator(".source-chips .tag.blue").count() == 1

    chip.click()
    dialog.get_by_role("button", name="All chats").first.click()
    expect(chip).to_have_text("All chats")


def test_empty_chat_review_ends_with_a_clear_message_and_no_spinner(page: Page, e2e_app) -> None:
    e2e_app.graph.empty_chats = True
    ask(page, "What needs my attention across the release team?")

    turn = page.locator(".turn.assistant.working")
    expect(turn).to_contain_text("Nothing to read in this chat yet")
    expect(turn).to_contain_text("Nothing was sent")
    expect(turn.locator(".spinner")).to_have_count(0)
    # A failed job offers Retry, not an endless Cancel/Resume.
    expect(turn.get_by_role("button", name="Retry")).to_be_visible()
    expect(turn.get_by_role("button", name="Resume")).to_have_count(0)
    assert e2e_app.graph.sent == []


def test_draft_from_instruction_in_an_empty_chat_is_labelled_and_still_needs_approval(
    page: Page, e2e_app
) -> None:
    e2e_app.graph.empty_chats = True
    ask(page, "Draft separate Teams messages to Parv and Meera to complete the planned items.")

    cards = page.locator(".planned-action .draft-card")
    expect(cards).to_have_count(2)
    for index in range(2):
        card = cards.nth(index)
        expect(card).to_contain_text("Based on your instruction")
        expect(card).to_contain_text("Awaiting approval")
        # Nothing is cited, so there is no evidence section to open.
        expect(card.locator("details.evidence")).to_have_count(0)
    assert e2e_app.graph.sent == []

    # The approval gate is unchanged: only an explicit approval sends, and only that card.
    cards.nth(0).get_by_role("button", name="Approve and send").click()
    expect(cards.nth(0)).to_contain_text("Sent")
    expect(cards.nth(1)).to_contain_text("Awaiting approval")
    assert len(e2e_app.graph.sent) == 1


def test_single_empty_group_chat_drafts_one_labelled_reply_to_that_group(
    page: Page, e2e_app
) -> None:
    e2e_app.graph.empty_chats = True
    chip = page.locator("#agent-source-chip")
    chip.click()
    page.locator("#agent-source-dialog").get_by_role("button", name="Release group").click()
    expect(chip).to_contain_text("Release group")

    ask(page, "draft a message to Parv and Rohan to complete the things we discussed earlier")

    card = page.locator(".draft-card")
    expect(card).to_have_count(1)
    expect(card).to_contain_text("Release group")
    expect(card).to_contain_text("Based on your instruction")
    expect(card).to_contain_text("Awaiting approval")
    expect(page.locator(".turn.assistant")).to_contain_text("What Prism could not verify")
    assert e2e_app.graph.sent == []

    card.get_by_role("button", name="Approve and send").click()
    expect(card).to_contain_text("Sent")
    assert [chat for chat, _ in e2e_app.graph.sent] == ["chat-release"]


def test_small_talk_is_answered_without_reading_teams(page: Page, e2e_app) -> None:
    box = page.locator("#agent-message-input")
    box.fill("hi")
    page.locator("#agent-send-button").click()
    reply = page.locator(".turn.assistant").first
    expect(reply).to_be_visible()
    expect(page.locator("#agent-timeline .say-typing")).to_have_count(0)
    # No review job, no evidence, no "Working on it" details: it was just a friendly answer.
    expect(page.locator(".turn-details")).to_have_count(0)
