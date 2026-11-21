from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.agent_sources import (
    TeamsChatSourceRead,
    TeamsSourceResolutionCandidate,
    TeamsSourceResolutionRead,
)
from app.services.errors import RuleViolationError
from app.services.teams_read_service import TeamsReadService


@dataclass(frozen=True)
class _Match:
    source: TeamsChatSourceRead
    score: int
    rationale: str
    match_key: str


class SourceResolutionService:
    """Deterministically resolve manager language against the authorized Teams catalog."""

    MAX_CANDIDATES = 8
    MAX_EXPLICIT_ALL_SOURCES = 12
    MAX_EXPLICIT_RECENT_SOURCES = 50

    @staticmethod
    def resolve(
        db: Session,
        goal: str,
        *,
        constrained_external_id: str | None = None,
        selected_external_id: str | None = None,
        selected_external_ids: list[str] | None = None,
        catalog: list[TeamsChatSourceRead] | None = None,
    ) -> TeamsSourceResolutionRead:
        # v2.2 passes a pre-filtered catalog here after applying its durable
        # Prism policy.  The v2.1 route keeps the historical full catalog.
        catalog = catalog if catalog is not None else TeamsReadService.list_sources(db)
        by_id = {item.external_id: item for item in catalog}
        limits = SourceResolutionService._limits()
        requested_history_days = SourceResolutionService._requested_history_days(goal)
        if requested_history_days is None and SourceResolutionService._is_auto_sweep(goal):
            requested_history_days = 1
        if requested_history_days is not None:
            limits = {
                **limits,
                "history_days": min(limits["history_days"], requested_history_days),
            }

        if constrained_external_id:
            source = by_id.get(constrained_external_id)
            if source is None:
                raise RuleViolationError(
                    "The source constraint is no longer available to the connected manager"
                )
            return SourceResolutionService._resolved(
                source,
                "You explicitly constrained this Prism conversation to this Teams chat.",
                "explicit_constraint",
                limits,
            )

        excluded = SourceResolutionService._excluded_sources(goal, catalog)
        selected_ids = list(dict.fromkeys(selected_external_ids or []))
        if selected_external_id and selected_external_id not in selected_ids:
            selected_ids.append(selected_external_id)
        if selected_ids:
            if len(selected_ids) > limits["sources"]:
                raise RuleViolationError(
                    f"Select at most {limits['sources']} Teams chats for one request"
                )
            sources = [by_id.get(external_id) for external_id in selected_ids]
            if any(source is None or source.external_id in excluded for source in sources):
                raise RuleViolationError(
                    "Choose a non-excluded Teams chat available to the connected manager"
                )
            return SourceResolutionService._resolved_many(
                [source for source in sources if source is not None],
                "You explicitly selected these Teams chats for this request.",
                "manager_choice",
                limits,
                excluded,
            )

        eligible_catalog = [item for item in catalog if item.external_id not in excluded]
        if requested_history_days is not None:
            activity_cutoff = datetime.now(timezone.utc) - timedelta(days=requested_history_days)
            eligible_catalog = [
                item
                for item in eligible_catalog
                if item.last_updated_at is not None and item.last_updated_at >= activity_cutoff
            ]
        private_scope = SourceResolutionService._requests_private_chats(goal)
        group_scope = SourceResolutionService._requests_group_chats(goal)
        if private_scope and not group_scope:
            eligible_catalog = [item for item in eligible_catalog if item.chat_type == "private"]
            if not eligible_catalog:
                raise RuleViolationError(
                    "No accessible 1:1 Teams chats had activity in the requested time window"
                )
        elif group_scope and not private_scope:
            eligible_catalog = [item for item in eligible_catalog if item.chat_type == "group"]
            if not eligible_catalog:
                raise RuleViolationError(
                    "No accessible Teams group chats had activity in the requested time window"
                )
        elif requested_history_days is not None and not eligible_catalog:
            raise RuleViolationError(
                "No accessible Teams chats had activity in the requested time window"
            )

        matches = [
            match
            for source in eligible_catalog
            if (match := SourceResolutionService._score(goal, source)) is not None
        ]
        matches.sort(
            key=lambda item: (
                item.score,
                item.source.last_updated_at.isoformat() if item.source.last_updated_at else "",
            ),
            reverse=True,
        )
        if matches:
            winners: list[_Match] = []
            ambiguous: list[_Match] = []
            for match_key in dict.fromkeys(item.match_key for item in matches):
                group = [item for item in matches if item.match_key == match_key]
                top_score = max(item.score for item in group)
                top = [item for item in group if item.score == top_score]
                if len(top) > 1:
                    ambiguous.extend(top)
                else:
                    winners.append(top[0])
            if ambiguous:
                auto_matches = {item.source.external_id: item for item in [*winners, *ambiguous]}
                selected_matches = list(auto_matches.values())[: limits["sources"]]
                return SourceResolutionService._resolved_many(
                    [item.source for item in selected_matches],
                    (
                        "Auto included every equally matching accessible Teams chat instead "
                        "of requiring a manual source choice."
                    ),
                    "auto_ambiguous",
                    limits,
                    excluded,
                )
            unique = {item.source.external_id: item for item in winners}
            selected_matches = list(unique.values())[: limits["sources"]]
            return SourceResolutionService._resolved_many(
                [item.source for item in selected_matches],
                " ".join(item.rationale for item in selected_matches),
                "deterministic_alias",
                limits,
                excluded,
            )

        available = eligible_catalog
        if len(available) == 1:
            return SourceResolutionService._resolved(
                available[0],
                "This is the only accessible Teams chat allowed by your request.",
                "only_available_source",
                limits,
                excluded,
            )
        if available and SourceResolutionService._requests_all_sources(goal):
            # An explicit request to read all/every chat is materially different
            # from a general team question. Honour it without opening a one-chat
            # picker, while retaining the API's hard upper bound.
            explicit_source_limit = (
                SourceResolutionService.MAX_EXPLICIT_RECENT_SOURCES
                if requested_history_days is not None
                else SourceResolutionService.MAX_EXPLICIT_ALL_SOURCES
            )
            all_source_limits = {
                **limits,
                "sources": explicit_source_limit,
            }
            selected = available[:explicit_source_limit]
            return SourceResolutionService._resolved_many(
                selected,
                (
                    "Selected every accessible Teams chat for this explicit all-sources request."
                    if len(available) <= explicit_source_limit
                    else f"Selected the {explicit_source_limit} most recently active "
                    "accessible Teams chats; "
                    "the request exceeded the per-review safety limit."
                ),
                "auto_all",
                all_source_limits,
                excluded,
            )
        if available and SourceResolutionService._is_broad_query(goal):
            selected = available[: limits["sources"]]
            return SourceResolutionService._resolved_many(
                selected,
                "Selected the most recently active accessible chats for this broad team question.",
                "auto_recent",
                limits,
                excluded,
            )
        if not available:
            raise RuleViolationError("No accessible Teams chats are available for this request")
        return SourceResolutionService._resolved_many(
            available[: limits["sources"]],
            (
                "Auto could not infer one specific source, so it selected the most recently "
                "active accessible Teams chats."
            ),
            "auto_default",
            limits,
            excluded,
        )

    @staticmethod
    def _resolved(
        source: TeamsChatSourceRead,
        rationale: str,
        selection_reason: str,
        limits: dict[str, int],
        excluded: set[str] | None = None,
    ) -> TeamsSourceResolutionRead:
        return SourceResolutionService._resolved_many(
            [source], rationale, selection_reason, limits, excluded
        )

    @staticmethod
    def _resolved_many(
        sources: list[TeamsChatSourceRead],
        rationale: str,
        selection_reason: str,
        limits: dict[str, int],
        excluded: set[str] | None = None,
    ) -> TeamsSourceResolutionRead:
        return TeamsSourceResolutionRead(
            status="resolved",
            selected=sources[0] if sources else None,
            selected_sources=sources,
            candidates=[],
            rationale=rationale,
            selection_reason=selection_reason,
            excluded_external_ids=sorted(excluded or set()),
            limits=limits,
        )

    @staticmethod
    def _candidate(match: _Match) -> TeamsSourceResolutionCandidate:
        return TeamsSourceResolutionCandidate(
            source=match.source,
            rationale=match.rationale,
            score=match.score,
        )

    @staticmethod
    def _score(goal: str, source: TeamsChatSourceRead) -> _Match | None:
        query = SourceResolutionService._inclusion_text(goal)
        scored_aliases: list[tuple[int, str, str]] = []
        label = SourceResolutionService._normalize(source.label)
        if label and SourceResolutionService._contains(query, label):
            scored_aliases.append((130, source.label, "chat name"))

        for participant in source.participant_details:
            full_name = SourceResolutionService._normalize(participant.display_name)
            if full_name and SourceResolutionService._contains(query, full_name):
                scored_aliases.append((115, participant.display_name, "participant"))
            first_name = full_name.split(" ", 1)[0]
            if len(first_name) >= 3 and SourceResolutionService._contains(query, first_name):
                scored_aliases.append((100, participant.display_name, "participant first name"))
            for alias in participant.aliases:
                normalized_alias = SourceResolutionService._normalize(alias)
                if len(normalized_alias) >= 2 and SourceResolutionService._contains(
                    query, normalized_alias
                ):
                    scored_aliases.append((120, alias, "saved person alias"))

        if not scored_aliases:
            return None
        score, matched, kind = max(scored_aliases)
        if source.chat_type == "private" and kind != "chat name":
            score += 15
        match_key = SourceResolutionService._normalize(matched)
        if kind == "participant first name":
            match_key = match_key.split(" ", 1)[0]
        return _Match(
            source=source,
            score=score,
            rationale=f"Matched {kind} “{matched}” in your request.",
            match_key=match_key,
        )

    @staticmethod
    def _is_broad_query(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        return any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "my team",
                "the team",
                "across the team",
                "all recent chats",
                "all chats",
                "overall update",
                "needs my attention",
                "what is going on",
                "what s going on",
            )
        )

    @staticmethod
    def _requests_all_sources(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        return SourceResolutionService._is_auto_sweep(goal) or bool(
            re.search(
                r"\b(?:all|every)\b(?:\s+[a-z0-9]+){0,4}\s+\b(?:chats?|sources?)\b",
                normalized,
            )
        )

    @staticmethod
    def _is_workspace_sweep(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        follow_up = bool(re.search(r"\bfollow\s*up\b", normalized)) and any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "anyone",
                "anybody",
                "someone",
                "who",
                "whom",
                "need to follow up",
                "should follow up",
            )
        )
        attention = any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "needs my attention",
                "need my attention",
                "what did i miss",
                "anything i missed",
                "unanswered messages",
                "waiting on me",
                "needs my reply",
                "need my reply",
                "need a reply from me",
            )
        )
        return follow_up or attention

    @staticmethod
    def _is_auto_sweep(goal: str) -> bool:
        return SourceResolutionService._is_workspace_sweep(
            goal
        ) or SourceResolutionService._is_source_category_sweep(goal)

    @staticmethod
    def _is_source_category_sweep(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        return any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "1v1 chats",
                "1 1 chats",
                "one on one chats",
                "private chats",
                "group chats",
                "teams groups",
            )
        )

    @staticmethod
    def _requests_private_chats(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        return any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "1v1 chat",
                "1v1 chats",
                "1 1 chat",
                "1 1 chats",
                "one on one chat",
                "one on one chats",
                "private chat",
                "private chats",
            )
        )

    @staticmethod
    def _requests_group_chats(goal: str) -> bool:
        normalized = SourceResolutionService._normalize(goal)
        return any(
            SourceResolutionService._contains(normalized, phrase)
            for phrase in (
                "group chat",
                "group chats",
                "teams group",
                "teams groups",
            )
        )

    @staticmethod
    def _requested_history_days(goal: str) -> int | None:
        normalized = SourceResolutionService._normalize(goal)
        if re.search(r"\b(?:last|past|previous)\s+24\s+hours?\b", normalized):
            return 1
        if SourceResolutionService._contains(normalized, "today"):
            return 1
        match = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+days?\b", normalized)
        return max(1, int(match.group(1))) if match else None

    @staticmethod
    def _excluded_sources(goal: str, catalog: list[TeamsChatSourceRead]) -> set[str]:
        normalized = SourceResolutionService._normalize(goal)
        clauses = re.findall(
            r"(?:do not|dont|exclude|except|without)\s+(?:read|check|use|include)?\s*([^,.!?;]+)",
            normalized,
        )
        excluded: set[str] = set()
        for clause in clauses:
            for source in catalog:
                aliases = [source.label, *source.participants]
                aliases.extend(
                    alias
                    for participant in source.participant_details
                    for alias in participant.aliases
                )
                if any(
                    len(candidate := SourceResolutionService._normalize(alias)) >= 2
                    and SourceResolutionService._contains(clause, candidate)
                    for alias in aliases
                ):
                    excluded.add(source.external_id)
        return excluded

    # "... and send it to Sanjay": the person after "to" receives the result, so they say nothing about
    # which chats to read.
    _SEND_CLAUSE = re.compile(
        r"\b(?:send|share|forward|post|message|dm|ping)\b(?:\s+\w+){0,8}?\s+(?:to|with)\s+(?P<who>.+)$"
    )

    @staticmethod
    def _inclusion_text(goal: str) -> str:
        normalized = SourceResolutionService._normalize(goal)
        normalized = re.split(
            r"\b(?:do not|dont|exclude|except|without)\b", normalized, maxsplit=1
        )[0]
        if SourceResolutionService._requests_all_sources(goal):
            normalized = SourceResolutionService._SEND_CLAUSE.split(normalized, maxsplit=1)[0]
        return normalized

    @staticmethod
    def destination_for(
        goal: str, catalog: list[TeamsChatSourceRead] | Callable[[], list[TeamsChatSourceRead]]
    ) -> TeamsChatSourceRead | None:
        """Who a "read all those chats and send it to X" request is addressed to, or None.

        Only for sweeps of many chats; a request about one named person keeps meaning that person's chat.
        The recipient's own 1:1 chat is used even when it had no activity in the reading window.
        """

        if not SourceResolutionService._requests_all_sources(goal):
            return None
        normalized = SourceResolutionService._normalize(goal)
        found = SourceResolutionService._SEND_CLAUSE.search(normalized)
        if found is None:
            return None
        who = SourceResolutionService._inclusion_text_for(found.group("who"))
        if callable(catalog):
            catalog = catalog()  # only fetched once the request is known to name a recipient
        matches = [
            match
            for source in catalog
            if source.chat_type == "private"
            and (match := SourceResolutionService._score(who, source)) is not None
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item.score, reverse=True)
        if len(matches) > 1 and matches[0].score == matches[1].score:
            return None  # two equally good people: never guess who gets it
        return matches[0].source

    @staticmethod
    def _inclusion_text_for(text: str) -> str:
        return re.split(r"\b(?:do not|dont|exclude|except|without)\b", text, maxsplit=1)[0]

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        return f" {phrase} " in f" {text} "

    @staticmethod
    def _normalize(value: str) -> str:
        folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", " ", folded.casefold()).strip()

    @staticmethod
    def _limits() -> dict[str, int]:
        settings = get_settings()
        return {
            "sources": settings.v21_teams_source_limit,
            "messages_per_source": settings.v21_teams_message_limit,
            "history_days": settings.v21_teams_history_days,
            "total_evidence_characters": settings.v21_teams_evidence_character_limit,
        }
