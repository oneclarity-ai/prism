from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MAX_TURNS = 60
DEFAULT_BUDGET_USD = 1.0
PRODUCTION_NOTE = (
    "Use synthetic test data only. Ask before payments, messages, deletions, publishing, "
    "account creation or other important changes, even with dummy data. "
    "Request secure login approval; never ask for credentials in chat."
)

_URL = re.compile(r"https?://[^\s<>\"')]+", re.I)
_DOMAIN = re.compile(
    r"(?<![@\w.-])((?:localhost|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24})(?::\d{2,5})?(?:/[^\s<>\"')]*)?)",
    re.I,
)
_NOT_SITES = {
    "js",
    "ts",
    "py",
    "md",
    "json",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "css",
    "html",
    "txt",
    "csv",
    "pdf",
    "yml",
    "yaml",
    "toml",
    "ini",
    "log",
    "zip",
    "exe",
    "dll",
    "so",
}
_PATH = re.compile(r"(?<![\w:/.])(/[a-z0-9][\w\-/]*)", re.I)
_TEST_INTENT = re.compile(
    r"\b(test|qa|smoke|regression|verify|validate|sanity|audit|check (?:out )?(?:the |my |our )?(?:site|website|web ?app|app|pages?|forms?))\b",
    re.I,
)
_SITE_WORDS = re.compile(r"\b(site|website|web ?app|webpage|pages?|forms?|app)\b", re.I)

QA_PLAN_PROMPT = """You are {name}, a QA tester on the manager's team. The manager asked you to test a website.
Turn the request into a short test plan. Use only what the manager actually asked for; never invent pages,
logins, or features. Discover internal pages automatically; the manager never needs to list routes.
pages are optional starting paths explicitly named by the manager, not an exhaustive page list.
Missing routes, login details or feature names are NOT reasons to ask for clarification.
features are short names of the areas to check (for example navigation, form validation).
acceptance_criteria are short Given/When/Then sentences, one per thing the manager wants verified.
If the request does not say what to test, return a sensible smoke test: key pages load, navigation works,
visible forms validate empty and invalid input. Follow the house rules; they limit what you may do.
If you truly cannot tell what site or area is meant, set needs_clarification and ask one short question.
Return only the required structured result."""


class QaPlanDraft(BaseModel):
    title: str = Field(default="", max_length=200)
    pages: list[str] = Field(default_factory=list, max_length=12)
    features: list[str] = Field(default_factory=list, max_length=12)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    needs_clarification: bool = False
    question: str = Field(default="", max_length=300)


class QaPlanError(Exception):
    """The request cannot become a plan; the message is written for the manager."""


def find_site(text: str) -> str | None:
    """The first site address in the message, normalised to scheme://host[:port]/path."""

    match = _URL.search(text)
    candidate = match.group(0) if match else None
    if candidate is None:
        for found in _DOMAIN.finditer(text):
            value = found.group(1).rstrip(".,;:!?")
            host = value.split("/")[0].split(":")[0].lower()
            if host.rsplit(".", 1)[-1] in _NOT_SITES:
                continue
            candidate = value
            break
    if candidate is None:
        return None
    candidate = candidate.rstrip(".,;:!?")
    if "://" not in candidate:
        host = candidate.split("/")[0].split(":")[0].lower()
        local = host == "localhost" or host.endswith(".local")
        candidate = f"{'http' if local else 'https'}://{candidate}"
    parts = urlsplit(candidate)
    if not parts.hostname:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def _is_private(host: str) -> bool:
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def environment_for(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if _is_private(host):
        return "local"
    if re.search(r"(^|[.-])(staging|stage|stg|dev|test|qa|uat|preview|sandbox)([.-]|$)", host):
        return "staging"
    return "production"


def wants_testing(text: str) -> bool:
    return bool(_TEST_INTENT.search(text))


def looks_like_test_request(text: str) -> bool:
    """A site address, or clearly asking for a test of a site/page/form, in a QA tester's chat."""

    if find_site(text) is not None:
        return bool(_TEST_INTENT.search(text)) or len(text.split()) <= 12
    return bool(_TEST_INTENT.search(text) and _SITE_WORDS.search(text))


class QaPlanService:
    @staticmethod
    def house_rules(db: Session, prism_id, thread_id) -> tuple[list[str], bool]:
        """Rules the manager gave this Prism, and whether it may ask to file bugs."""

        from app.models.prisms.prism_v22 import PrismWorkingAgreement
        from app.services.prisms.agent_preference_service import AgentPreferenceService

        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(PrismWorkingAgreement.prism_id == prism_id)
            .order_by(PrismWorkingAgreement.revision.desc())
        )
        content = agreement.agreement if agreement else {}
        rules: list[str] = []
        restrictions = str(content.get("restrictions") or "").strip()
        if restrictions and not restrictions.startswith("No additional restrictions"):
            rules.append(restrictions[:600])
        for item in AgentPreferenceService.active(db, thread_id=thread_id)[:8]:
            rules.append(item.instruction[:300])
        proposals = " ".join(content.get("allowed_proposals") or []).casefold()
        return rules, "file bugs" in proposals

    @classmethod
    def build(cls, db: Session, *, prism, thread_id, text: str) -> dict:
        """A plan the manager can approve. Raises QaPlanError when it cannot be made safely."""

        from app.services.llm.llm_service import LLMService

        settings = get_settings()
        site = find_site(text)
        if site is None:
            raise QaPlanError("Which site should I test? Send me the address and what to check.")
        parts = urlsplit(site)
        try:
            port = parts.port
        except ValueError as exc:
            raise QaPlanError("Send a website URL with a valid port.") from exc
        if parts.username or parts.password:
            raise QaPlanError(
                "Send a website URL without login details. Use the secure login card later."
            )
        host = urlsplit(site).hostname or ""
        environment = environment_for(site)
        if environment == "local" and not settings.qa_allow_local_targets:
            raise QaPlanError("I can only test public sites from here, not local addresses.")
        rules, may_file_bugs = cls.house_rules(db, prism.id, thread_id)

        draft = QaPlanDraft()
        try:
            draft = LLMService.complete(
                prompt=QA_PLAN_PROMPT.format(name=prism.name),
                context={
                    "request": " ".join(text.split())[:4000],
                    "site": site,
                    "house_rules": rules,
                },
                output_model=QaPlanDraft,
                feature="prism_qa_plan",
            )
        except Exception:  # noqa: BLE001 - the plan still works from the plain request
            logger.info("qa_plan_model_unavailable", exc_info=False)
        authority = f"[{host}]" if ":" in host else host
        if port and port != (443 if parts.scheme == "https" else 80):
            authority += f":{port}"
        base = f"{parts.scheme}://{authority}"
        # Only the request supplies seeds. A model must not invent a mandatory route list.
        pages = cls._clean_pages(
            [urlsplit(site).path or "", *(m.group(1) for m in _PATH.finditer(text))]
        )
        notes = [
            PRODUCTION_NOTE,
            "Discover all reachable internal pages, menus and client-side routes on the starting "
            "origin. Ask before entering any other origin, including subdomains. Record tested "
            "and untested pages with reasons. Ask to extend the approved budget before stopping; "
            "never continue beyond a limit without approval.",
        ]
        notes += rules
        return {
            "site": base,
            "host": host,
            "environment": environment,
            "title": (draft.title.strip() or f"Test {host}")[:200],
            "request": " ".join(text.split())[:4000],
            "pages": pages or ["/"],
            "discovery_mode": "automatic",
            "allowed_origins": [base],
            "form_policy": "synthetic_with_approval",
            "request_login": True,
            "request_budget_extension": True,
            "features": [f[:120] for f in draft.features if f.strip()][:12]
            or ["navigation", "form validation"],
            "acceptance_criteria": [c[:300] for c in draft.acceptance_criteria if c.strip()][:12],
            "notes": "\n".join(notes)[:2000],
            "max_turns": min(DEFAULT_MAX_TURNS, settings.qa_max_turns_cap),
            "budget_usd": min(DEFAULT_BUDGET_USD, settings.qa_budget_cap_usd),
            "allow_bug_filing": False,
            "may_file_bugs": may_file_bugs,
            "mode": "single",
        }

    @staticmethod
    def _clean_pages(items: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for item in items:
            value = str(item).strip()
            if not value:
                continue
            if not value.startswith("/"):
                value = "/" + value
            value = value.split("?")[0].split("#")[0].rstrip("/") or "/"
            if len(value) <= 200 and re.fullmatch(r"/[\w\-./%]*", value):
                seen.setdefault(value, None)
        return list(seen)[:12]

    @staticmethod
    def apply_edits(plan: dict, edits: dict | None) -> dict:
        """Manager edits to a plan, clamped by the server so the browser never sets the limits."""

        settings = get_settings()
        plan = dict(plan)
        edits = edits or {}
        if "pages" in edits:
            plan["pages"] = QaPlanService._clean_pages(list(edits["pages"] or [])) or ["/"]
        for key in ("features", "acceptance_criteria"):
            if key in edits:
                plan[key] = [str(v).strip()[:300] for v in (edits[key] or []) if str(v).strip()][
                    :12
                ]
        if edits.get("max_turns") is not None:
            plan["max_turns"] = max(5, min(int(edits["max_turns"]), settings.qa_max_turns_cap))
        if edits.get("budget_usd") is not None:
            plan["budget_usd"] = round(
                max(0.1, min(float(edits["budget_usd"]), settings.qa_budget_cap_usd)), 2
            )
        if "allow_bug_filing" in edits:
            # Bug filing needs the Prism's agreement to allow it and a production site is never filed on.
            plan["allow_bug_filing"] = bool(
                edits["allow_bug_filing"]
                and plan.get("may_file_bugs")
                and plan.get("environment") != "production"
            )
        return plan
