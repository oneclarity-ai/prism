"""Deterministic first-pass classification for ordinary employee messages.

This module deliberately answers a smaller question than the LLM: what kinds of
facts are literally present in the latest message?  It never binds a message to
an old blocker, chooses an employee, or authorises a state mutation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentName = Literal[
    "courtesy",
    "work_update",
    "completion",
    "blocker",
    "commitment",
    "correction",
    "question",
    "contextual_answer",
    "conversation",
]


@dataclass(frozen=True)
class MessageSignals:
    intent: IntentName
    normalized: str
    tokens: tuple[str, ...]
    courtesy_only: bool
    explicit_no_blocker: bool
    blocker: bool
    owner_unknown: bool
    completion: bool
    progress: bool
    commitment: bool
    correction: bool
    question: bool
    contextual_answer: bool


class MessageIntentService:
    """Classify literal message signals without using conversation history."""

    COURTESY_WORDS = {
        "hi",
        "hello",
        "hey",
        "sir",
        "maam",
        "mam",
        "ji",
        "ok",
        "okay",
        "sure",
        "yes",
        "yeah",
        "yep",
        "thanks",
        "thank",
        "you",
        "got",
        "it",
        "noted",
        "fine",
        "for",
        "the",
        "update",
    }
    PROGRESS_WORDS = {
        "working",
        "testing",
        "reviewing",
        "validating",
        "checking",
        "implementing",
        "building",
        "fixing",
        "developing",
        "deploying",
        "investigating",
        "debugging",
        "preparing",
        "writing",
        "updating",
        "continuing",
        "integrating",
        "refactoring",
    }
    COMPLETION_WORDS = {
        "done",
        "finished",
        "completed",
        "shipped",
        "deployed",
        "fixed",
        "resolved",
        "delivered",
        "closed",
        "wrapped",
    }
    BLOCKER_WORDS = {
        "blocked",
        "blocker",
        "blocking",
        "stuck",
        "waiting",
        "dependency",
        "dependencies",
        "pending",
        "missing",
        "cannot",
        "can't",
    }
    CORRECTION_WORDS = {"actually", "correction", "instead", "rather"}
    QUESTION_WORDS = {
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "how",
        "can",
        "could",
        "should",
        "is",
        "are",
        "do",
    }
    ANSWER_WORDS = {
        "yes",
        "no",
        "done",
        "completed",
        "tomorrow",
        "today",
        "sure",
        "okay",
        "sent",
        "shared",
        "delivered",
        "finished",
    }

    @staticmethod
    def analyze(content: str) -> MessageSignals:
        normalized = " ".join(content.casefold().replace("’", "'").split())
        tokens = tuple(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", normalized))
        token_set = set(tokens)
        courtesy_only = bool(tokens) and token_set <= MessageIntentService.COURTESY_WORDS
        explicit_no_blocker = bool(
            re.search(
                r"\b(?:no|without)\s+(?:(?:dependency|dependencies)\s+(?:or|and)\s+)?"
                r"(?:blocker|blockers)\b|\bno\s+(?:dependency|dependencies)\b|"
                r"\bnot\s+blocked\b|\bnothing\s+(?:is\s+)?block(?:ed|ing)\b",
                normalized,
            )
        )
        owner_unknown = bool(
            re.search(
                r"\b(?:i\s+)?(?:still\s+)?(?:do\s+not|don't)\s+know\s+"
                r"(?:who\s+owns\s+it|the\s+owner)\b|"
                r"\b(?:still\s+)?not\s+sure\s+who\s+owns\s+it\b|"
                r"\b(?:the\s+)?owner\s+is\s+(?:still\s+)?unknown\b|\bunknown\s+owner\b",
                normalized,
            )
        )
        # People often describe a dependency conversationally rather than using
        # the word "blocked": "I need help of Morgan" and "we need support
        # from Bailey" are blocker reports when a real person can be resolved by
        # the response layer.  Keep this bounded to a request for help/input/
        # support so ordinary phrases such as "we need the deployment" are not
        # promoted into a dependency by themselves.
        named_help_request = bool(
            re.search(
                r"\bneed(?:ed|s)?\b.{0,80}\b(?:help|input|support|assistance)\b\s+(?:from|of)\b",
                normalized,
            )
        )
        blocker = not explicit_no_blocker and (
            bool(token_set & MessageIntentService.BLOCKER_WORDS)
            or bool(re.search(r"\bneed(?:ed|s)?\b.{0,80}\bfrom\b", normalized))
            or named_help_request
        )
        completion = (
            bool(token_set & MessageIntentService.COMPLETION_WORDS) or "wrapped up" in normalized
        )
        progress = bool(token_set & MessageIntentService.PROGRESS_WORDS) or bool(
            re.search(r"\b(?:work|focus)(?:ing)?\s+on\b|\bin\s+progress\b", normalized)
        )
        commitment = bool(
            re.search(
                r"\b(?:i\s*(?:will|'ll)|we\s*(?:will|'ll)|plan(?:ning)?\s+to|expect(?:ing)?\s+to)\b",
                normalized,
            )
        )
        correction = bool(token_set & MessageIntentService.CORRECTION_WORDS) or bool(
            re.search(r"\bnot\b.{0,60}\b(?:but|instead)\b", normalized)
        )
        question = "?" in content or (
            bool(tokens) and tokens[0] in MessageIntentService.QUESTION_WORDS
        )
        has_time_answer = bool(
            re.search(
                r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
                r"\b\d{1,2}(?::|\.)?\d{0,2}\s*(?:am|pm)\b",
                normalized,
            )
        )
        contextual_answer = (
            len(tokens) <= 10
            and not progress
            and not blocker
            and not question
            and (bool(token_set & MessageIntentService.ANSWER_WORDS) or has_time_answer)
        )

        if courtesy_only and not contextual_answer:
            intent: IntentName = "courtesy"
        elif blocker:
            intent = "blocker"
        elif correction:
            intent = "correction"
        elif completion:
            intent = "completion"
        elif progress:
            intent = "work_update"
        elif commitment:
            intent = "commitment"
        elif question:
            intent = "question"
        elif contextual_answer:
            intent = "contextual_answer"
        else:
            intent = "conversation"
        return MessageSignals(
            intent=intent,
            normalized=normalized,
            tokens=tokens,
            courtesy_only=courtesy_only,
            explicit_no_blocker=explicit_no_blocker,
            blocker=blocker,
            owner_unknown=owner_unknown,
            completion=completion,
            progress=progress,
            commitment=commitment,
            correction=correction,
            question=question,
            contextual_answer=contextual_answer,
        )

    @staticmethod
    def split_progress(content: str) -> tuple[str | None, str | None]:
        """Extract broad completed/current clauses without claiming task identity."""

        raw = content.strip()
        boundary = re.search(
            r"(?:[,.;]\s*|\s+)\b(?:and\s+)?(?:now|currently)\b",
            raw,
            flags=re.I,
        )
        if boundary is None:
            signals = MessageIntentService.analyze(raw)
            return (
                raw if signals.completion else None,
                raw if signals.progress or not signals.completion else None,
            )
        before = raw[: boundary.start()].strip(" ,.;")
        after = raw[boundary.start() :].strip(" ,.;")
        after = re.sub(r"^(?:and\s+)?(?:now|currently)\s+", "", after, flags=re.I)
        return before or None, after or None
