from __future__ import annotations

import pytest

from app.services.prisms.chat_intent_service import ChatIntentService


def _reply(text: str) -> str | None:
    return ChatIntentService.reply(text, prism_name="Ops", prism_description="Watches releases.")


@pytest.mark.parametrize(
    "text",
    ["hi", "Hello there!", "hey prism", "thanks", "Thank you so much", "ok", "bye", "how are you?"],
)
def test_small_talk_gets_a_reply_without_reading_teams(text: str) -> None:
    assert _reply(text)


def test_identity_question_uses_the_prism_description() -> None:
    reply = _reply("who are you?")
    assert reply and "Ops" in reply and "Watches releases" in reply


@pytest.mark.parametrize(
    "text",
    [
        "what is happening in the release chat",
        "hi, anything from Parv today?",
        "summarize my chats",
        "ok send it",
        "draft a message to Meera",
        "",
        "hello " + "x" * 80,
    ],
)
def test_anything_about_work_still_reads_teams(text: str) -> None:
    assert _reply(text) is None


def test_the_same_message_gets_the_same_reply() -> None:
    assert _reply("hi") == _reply("hi")


def test_review_prompt_asks_for_a_real_summary_not_pasted_chat() -> None:
    from app.services.management.conversation_review_service import REVIEW_PROMPT

    assert "Never paste, quote, or string together raw" in REVIEW_PROMPT
    assert "the message is the summary itself" in REVIEW_PROMPT
