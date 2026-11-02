from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.brain_service import BrainService
from app.services.prism_presets import ALWAYS_ASKS_FIRST, uses_labels
from app.services.qa_plan_service import (
    _DOMAIN,
    _NOT_SITES,
    _URL,
    QaPlanError,
    QaPlanService,
    environment_for,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TURNS = 120
DEFAULT_BUDGET_USD = 2.0

_TEAMS_WORDS = re.compile(r"\b(teams|chats?|dm|conversations?|threads?|slack)\b", re.I)
# Teams used as the thing to act on ("in Teams", "my chats", "the Teams chat"), not just named as a tool.
_TEAMS_ACTION = re.compile(
    r"\b(?:in|on|from|via|through|over)\s+(?:the\s+|my\s+|our\s+)?(?:microsoft\s+)?(?:teams|slack)\b"
    r"|\b(?:my|our|the|all)\s+(?:(?:microsoft\s+)?teams\s+|slack\s+)?(?:chats?|dms?|conversations?|threads?)\b"
    r"|\b(?:in|on|from)\s+(?:the|my|our)\s+(?:chat|thread|conversation)\b"
    r"|\b(?:teams|slack)\s+(?:chats?|messages?|dms?|threads?|conversations?)\b",
    re.I,
)
_VERBS = re.compile(
    r"\b(find|search|look ?up|research|check|compare|collect|gather|visit|open|go to|browse|extract|"
    r"download|scrape|fill|book|track|monitor|pull|identify|get me|read|list|investigate|fetch)\b",
    re.I,
)
_WEBISH = re.compile(
    r"\b(online|web|website|webpage|google|linkedin|internet|news|competitors?|companies|leads|"
    r"prices?|pricing|jobs?|listings?|reviews?|profiles?|directory|portal|dashboard|site|sites)\b",
    re.I,
)
_QUESTION = re.compile(
    r"^(what|why|how|who|when|where|which|can you|could you tell|do you|are you)\b", re.I
)

WORK_PLAN_PROMPT = """You are {name}. Your job: {description}.
The manager asked you to do a task in your own web browser. Turn it into a short plan.
Use only what was asked; never invent sites, accounts or facts.
steps: 3 to 7 short imperative steps (under 14 words each). sites: web addresses the manager named (leave
empty when none). any_public_site: true when you must search or visit sites that were not named.
If you truly cannot tell what to do, set needs_clarification and ask one short question.
Follow the house rules; they limit what you may do. Return only the required structured result."""

TASK_PROMPT = """Decide if the manager's message asks {name} to DO something on the web in its own browser
(research, look things up, collect or compare information, fill or use a website), as opposed to asking a
question, chatting, or asking about earlier results or Teams. Return task=true only for the first kind."""


class WorkPlanDraft(BaseModel):
    title: str = Field(default="", max_length=200)
    steps: list[str] = Field(default_factory=list, max_length=8)
    sites: list[str] = Field(default_factory=list, max_length=8)
    any_public_site: bool = False
    needs_clarification: bool = False
    question: str = Field(default="", max_length=300)


class _TaskCheck(BaseModel):
    task: bool


def find_sites(text: str) -> list[str]:
    """Every site address in the message as scheme://host[:port], in order, without repeats."""

    found: dict[str, None] = {}
    for match in _URL.finditer(text):
        parts = urlsplit(match.group(0).rstrip(".,;:!?"))
        if parts.hostname:
            found.setdefault(f"{parts.scheme.lower()}://{parts.netloc.lower()}", None)
    for match in _DOMAIN.finditer(text):
        value = match.group(1).rstrip(".,;:!?")
        host = value.split("/")[0].split(":")[0].lower()
        if host.rsplit(".", 1)[-1] in _NOT_SITES:
            continue
        local = host == "localhost" or host.endswith(".local")
        parts = urlsplit(f"{'http' if local else 'https'}://{value}")
        if parts.hostname:
            found.setdefault(f"{parts.scheme}://{parts.netloc.lower()}", None)
    return list(found)[:8]


def looks_like_task(db: Session | None, name: str, text: str) -> bool:
    """A request to do something on the web. Clear cases need no model call."""

    normalized = " ".join(text.split())
    verb = bool(_VERBS.search(normalized))
    sites = find_sites(normalized)
    # A long research brief may merely name Teams or Slack as tools; only veto when it acts on them.
    if _TEAMS_WORDS.search(normalized) and (
        _TEAMS_ACTION.search(normalized) or not (sites or _WEBISH.search(normalized))
    ):
        return False
    if not verb:
        return False
    if sites or _WEBISH.search(normalized):
        return True
    if _QUESTION.match(normalized) or len(normalized.split()) < 5:
        return False
    from app.services.llm_service import LLMService

    try:
        return LLMService.complete(
            prompt=TASK_PROMPT.format(name=name),
            context={"message": normalized[:800]},
            output_model=_TaskCheck,
            feature="prism_work_intent",
        ).task
    except Exception:  # noqa: BLE001 - unclear and no model: treat it as chat
        return False


def _clean_steps(items: list[str]) -> list[str]:
    return [" ".join(str(i).split())[:200] for i in items if str(i).strip()][:7]


class WorkPlanService:
    @classmethod
    def build(cls, db: Session, *, prism, thread_id, text: str) -> dict:
        from app.services.llm_service import LLMService

        settings = get_settings()
        request = " ".join(text.split())[:1500]
        named = find_sites(text)
        for site in named:
            if environment_for(site) == "local" and not settings.qa_allow_local_targets:
                raise QaPlanError("I can only use public sites from here, not local addresses.")
        rules, _ = QaPlanService.house_rules(db, prism.id, thread_id)

        draft = WorkPlanDraft()
        try:
            draft = LLMService.complete(
                prompt=WORK_PLAN_PROMPT.format(
                    name=prism.name, description=prism.description[:500]
                ),
                context={
                    "request": request,
                    "named_sites": named,
                    "house_rules": rules,
                    "about_the_organisation": BrainService.context(db),
                },
                output_model=WorkPlanDraft,
                feature="prism_work_plan",
            )
        except Exception:  # noqa: BLE001 - the plan still works from the plain request
            logger.info("work_plan_model_unavailable", exc_info=False)
        if draft.needs_clarification and draft.question.strip():
            raise QaPlanError(draft.question.strip())

        sites = named or find_sites(" ".join(draft.sites))
        steps = _clean_steps(draft.steps) or [
            "Work out exactly what is needed",
            "Do the work in my browser",
            "Collect what I found",
            "Report back to you",
        ]
        any_public = draft.any_public_site or not sites
        return {
            "kind": "work",
            "title": (draft.title.strip() or request[:80])[:200],
            "request": request,
            "steps": steps,
            "sites": sites,
            "any_public_site": any_public,
            "uses": uses_labels(prism.capabilities or ["browser"]),
            "asks_first": cls.asks_first(prism),
            "notes": "\n".join(rules)[:2000],
            "max_turns": min(DEFAULT_MAX_TURNS, settings.work_max_turns_cap),
            "budget_usd": min(DEFAULT_BUDGET_USD, settings.work_budget_cap_usd),
            "max_minutes": settings.work_max_minutes,
        }

    @staticmethod
    def asks_first(prism) -> list[str]:
        items = list(ALWAYS_ASKS_FIRST)
        if prism.logins_policy != "ask":
            items = [i for i in items if not i.startswith("Signing in")]
        return items

    @staticmethod
    def apply_edits(plan: dict, edits: dict | None) -> dict:
        """Manager edits, clamped by the server so the browser never sets the limits."""

        settings = get_settings()
        plan = dict(plan)
        edits = edits or {}
        if "steps" in edits:
            plan["steps"] = _clean_steps(list(edits["steps"] or [])) or plan["steps"]
        if "sites" in edits:
            plan["sites"] = find_sites(" ".join(str(s) for s in (edits["sites"] or [])))
            plan["any_public_site"] = bool(edits.get("any_public_site", not plan["sites"]))
        if edits.get("max_turns") is not None:
            plan["max_turns"] = max(5, min(int(edits["max_turns"]), settings.work_max_turns_cap))
        if edits.get("budget_usd") is not None:
            plan["budget_usd"] = round(
                max(0.1, min(float(edits["budget_usd"]), settings.work_budget_cap_usd)), 2
            )
        return plan

    @staticmethod
    def origins(plan: dict) -> list[str]:
        """Where the computer's browser may go. Empty means any public site (the plan said so)."""

        return [] if plan.get("any_public_site") else list(plan.get("sites") or [])
