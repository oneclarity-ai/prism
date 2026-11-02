from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.prism_v22 import Prism
from app.models.qa import QA_ACTIVE_STATES, QaApproval, QaRun
from app.services.agent_preference_service import AgentPreferenceService
from app.services.brain_service import BrainService
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prism_agent_service import PrismAgentService
from app.services.qa_plan_service import (
    QaPlanError,
    QaPlanService,
    find_site,
    looks_like_test_request,
)
from app.services.qa_swarm_client import QaSwarmClient, SwarmError
from app.services.work_plan_service import WorkPlanService, looks_like_task

logger = logging.getLogger(__name__)

_SWARM_TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}
_STATE_FOR = {
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "timed_out": "timed_out",
}
LOG_LIMIT = 40
OFFLINE_GRACE = timedelta(minutes=3)


def make_client() -> QaSwarmClient:
    """Tests replace this with a client backed by a fake swarm."""

    return QaSwarmClient()


DRAFT_RULE = (
    "If they ask for a draft message to someone or to a group, never put the message in reply. Put the "
    "message itself in draft_body (written by you to the recipient as the manager's assistant: friendly, "
    "specific, the manager named by first name in the third person; in the opening line say who you are as the "
    "manager's assistant for your own job, using your name above, never as a chief of staff or any other role; "
    "put each company, finding or point on its own line as '- Name: detail' using the real names, websites and "
    "facts from my_work_results, never placeholders like [Website] or 'Company A', and keep what was only an "
    "estimate or still unverified marked as such; no 'draft' label, no offers "
    "or questions for the manager, no sign-off) and who it is for in draft_to: the person's name, several names joined with ' and ', or "
    "the group chat's name when they name one. Then reply is one short line such as 'Here's a draft for "
    "Sanjay and Ajay. Edit it and send when you're ready.' Nothing is sent until the manager sends it."
)


class _Answer(BaseModel):
    reply: str = Field(default="", max_length=4000)
    needs_other_help: bool = False
    draft_to: str = Field(default="", max_length=120)
    draft_body: str = Field(default="", max_length=3500)


FOLLOW_UP_PROMPT = """You are {name}, a QA tester on the manager's team, chatting privately with the manager.
Sound like a real colleague: plain, direct, warm, no sign-offs. Answer from my_test_results only: what you
tested, what failed or could not be checked, the issues you found, and what you would fix or focus on
first, most important first (a short list is fine when listing fixes). Never invent results, pages or bugs.
If there are no results yet, say so and offer to test a site (you show a plan first). If a test is running
now, say what you know so far.
If the manager asks for a report, write it: what was tested, the outcome with counts, the issues by
severity with steps, expected and actual, and recommended next steps. {draft_rule}
You do not read Microsoft Teams here. If the message needs what people said in Teams, or is unrelated to
testing and websites, set needs_other_help to true and leave reply empty. Greetings and small talk about
you or your work can be answered briefly.
Return only the required structured result."""

WORK_FOLLOW_UP_PROMPT = """You are {name}, an assistant on the manager's team, chatting privately with the manager.
Your job: {description}. You do web tasks in your own browser and bring back results.
Sound like a real colleague: plain, direct, warm, no sign-offs. Answer from my_work_results only: what you
did, what you found, what you could not do, and what to do next. Never invent results or sources.
If a task is running now, say what you know so far. If the manager asks for a report, write it from the
results. {draft_rule} You do not read Microsoft Teams here. If the message needs what people said in Teams, or is
unrelated to your work, set needs_other_help to true and leave reply empty. Greetings and small talk
about you or your work can be answered briefly.
Return only the required structured result."""

_TEAMS_INTENT = re.compile(r"\b(teams|chats?|dm|conversations?|threads?|slack)\b", re.I)
# Asking about the Prism's own findings ("the 10 companies you found"): Teams is then only where it goes.
_MY_RESULTS = re.compile(
    r"\byou\s+(?:found|researched|collected|compiled|listed)\b"
    r"|\b(?:this|these|those|the|my|your)\s+(?:\d+\s+)?(?:\w+\s+)?"
    r"(?:companies|results?|findings?|list|report|csv|leads|prospects)\b",
    re.I,
)
_DRAFTING = re.compile(r"\b(draft|write|compose|prepare|create|make)\b", re.I)
_ABOUT_MY_WORK = re.compile(
    r"\b(report|draft|results?|issues?|bugs?|fix\w*|fail\w*|findings?|write[- ]?up)\b", re.I
)
_ABOUT_RESULTS = re.compile(
    r"\b(change|changes|fix|fixes|focus|issues?|bugs?|fail\w*|results?|report|found|improve\w*|suggest\w*|"
    r"recommend\w*|priority|priorities|next|wrong|problems?|errors?|pass\w*|summary|how did the test|how did it go|"
    r"draft|share|send|tell|this|these|those)\b",
    re.I,
)


class _Summary(BaseModel):
    summary: str = Field(max_length=900)


SUMMARY_PROMPT = """You are {name}, a QA tester, writing up a finished website test for the manager in your
own voice: two to four plain sentences, no headings, no bullet points, no sign-off. Say what you tested,
how it went (counts of passed and failed checks) and the most important thing they should know. Use
only the facts given; never invent results. If something could not be checked, say so honestly.
Never mention field names, data, or internal systems: speak like a colleague.
Return only the required structured result."""


class _WorkSummary(BaseModel):
    summary: str = Field(max_length=900)
    needs_attention: list[str] = Field(default_factory=list, max_length=4)
    next_steps: list[str] = Field(default_factory=list, max_length=3)


WORK_SUMMARY_PROMPT = """You are {name}, writing up a finished task for the manager in your own voice: two to
four plain sentences, no headings, no sign-off. Say what you did, what you found (counts), and the one thing
they most need to know. Use only the facts given; never invent results. If something could not be done, say
so honestly. Follow any manager_instructions about how to write to them. Never mention field names or internal systems. needs_attention: up to 4 short things you were unsure about or could not do (empty if none).
next_steps: up to 3 short follow-ups you could offer. Return only the required structured result."""

_TOOL_TEXT: dict[str, Callable[[dict], str]] = {
    "browser_navigate": lambda a: f"Opening {a.get('url') or 'a page'}",
    "browser_navigate_back": lambda a: "Going back",
    "browser_snapshot": lambda a: "Reading the page",
    "browser_find": lambda a: f"Looking for '{str(a.get('text') or a.get('query') or '')[:60]}'",
    "browser_click": lambda a: f"Clicking '{str(a.get('element') or 'an element')[:60]}'",
    "browser_type": lambda a: f"Typing in '{str(a.get('element') or 'a field')[:60]}'",
    "browser_fill_form": lambda a: "Filling in the form",
    "browser_select_option": lambda a: f"Choosing an option in '{str(a.get('element') or 'a menu')[:60]}'",
    "browser_press_key": lambda a: f"Pressing {a.get('key') or 'a key'}",
    "browser_hover": lambda a: f"Hovering over '{str(a.get('element') or 'an element')[:60]}'",
    "browser_wait_for": lambda a: "Waiting for the page",
    "browser_handle_dialog": lambda a: "Handling a dialog",
    "browser_take_screenshot": lambda a: "Taking a screenshot",
    "browser_console_messages": lambda a: "Checking the browser console",
    "browser_tabs": lambda a: "Switching tabs",
    "get_task_context": lambda a: "Reading the test brief",
    "get_test_login": lambda a: "Signing in",
    "save_test_plan": lambda a: "Writing the test plan",
    "record_test_result": lambda a: f"Recording a result: {str(a.get('case') or '')[:70]}".rstrip(
        ": "
    ),
    "draft_bug": lambda a: f"Drafting a bug: {str(a.get('title') or '')[:70]}".rstrip(": "),
    "file_bug": lambda a: "Asking to file a bug",
    "complete_task": lambda a: "Wrapping up",
    "add_note": lambda a: "Writing a note",
    "update_checklist": lambda a: "Updating my plan",
    "save_file": lambda a: f"Saving {str(a.get('name') or 'a file')[:60]}",
    "ask_manager": lambda a: "Asking you a question",
    "confirm_action": lambda a: "Checking with you before I go on",
    "request_login": lambda a: "Asking you for a login",
    "sign_in": lambda a: "Signing in",
    "teams_search": lambda a: "Searching your Teams chats",
    "teams_read_chat": lambda a: "Reading a Teams chat",
    "teams_draft_message": lambda a: "Drafting a Teams message",
}


def activity_text(tool: str, arguments: dict | None) -> str:
    handler = _TOOL_TEXT.get(tool)
    args = arguments if isinstance(arguments, dict) else {}
    if handler is None:
        return "Working"
    return handler(args)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


class QaRunService:
    # ---------- availability ----------

    @staticmethod
    def available() -> tuple[bool, str | None]:
        if not get_settings().qa_swarm_configured:
            return False, "My testing workspace isn't set up yet. Ask your admin to set it up."
        return True, None

    @staticmethod
    def is_qa_prism(prism: Prism | None) -> bool:
        return prism is not None and prism.template_key == "qa_tester"

    @staticmethod
    def is_work_prism(prism: Prism | None) -> bool:
        """Any Prism that is not a QA tester, once v2.4 gives every Prism a computer."""

        return (
            prism is not None
            and prism.template_key != "qa_tester"
            and get_settings().prism_v24_enabled
        )

    # ---------- chat: plan ----------

    @classmethod
    def handle_chat(cls, db: Session, *, thread_id: uuid.UUID, text: str) -> dict:
        """Turn a test request into a plan card (or a question). handled=False means not a test request."""

        thread = db.get(AgentThread, thread_id)
        if thread is None:
            raise NotFoundError("Agent conversation was not found")
        prism = db.get(Prism, thread.prism_id) if thread.prism_id else None
        if cls.is_work_prism(prism):
            return cls._handle_work_chat(db, thread, prism, text)
        if not cls.is_qa_prism(prism):
            return {"handled": False}
        # An answer to my own question continues the earlier request instead of replacing it.
        last = db.scalar(
            select(AgentThreadMessage)
            .where(AgentThreadMessage.thread_id == thread.id)
            .order_by(AgentThreadMessage.created_at.desc())
            .limit(1)
        )
        meta = (last.message_metadata or {}) if last is not None else {}
        request = text
        if (
            last is not None
            and meta.get("kind") == "qa_question"
            and (find_site(text) or looks_like_test_request(text))
        ):
            request = f"{meta.get('request', '')}\n\nManager's answer to my question: {text}"
        elif not looks_like_test_request(text):
            return cls._follow_up(db, thread, prism, text)

        now = _now()
        db.add(
            AgentThreadMessage(thread_id=thread.id, role="manager", content=text, created_at=now)
        )
        later = now + timedelta(milliseconds=5)
        ok, reason = cls.available()
        if not ok:
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id, role="assistant", content=reason, created_at=later
                )
            )
            thread.updated_at = now
            db.commit()
            return {"handled": True}
        try:
            plan = QaPlanService.build(db, prism=prism, thread_id=thread.id, text=request)
        except QaPlanError as exc:
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id,
                    role="assistant",
                    content=str(exc),
                    message_metadata={"kind": "qa_question", "request": request[:4000]},
                    created_at=later,
                )
            )
            thread.updated_at = now
            db.commit()
            return {"handled": True}

        run = QaRun(prism_id=prism.id, thread_id=thread.id, state="planned", plan=plan)
        db.add(run)
        db.flush()
        db.add(
            AgentThreadMessage(
                thread_id=thread.id,
                role="assistant",
                content=cls._plan_intro(prism, plan),
                message_metadata={"kind": "qa_plan", "qa_run_id": str(run.id)},
                created_at=later,
            )
        )
        thread.updated_at = now
        db.commit()
        return {"handled": True, "qa_run_id": run.id}

    # ---------- chat: tasks for a Prism's own computer ----------

    @classmethod
    def _reply(cls, db: Session, thread: AgentThread, text: str, reply: str, extra=None) -> dict:
        now = _now()
        db.add(
            AgentThreadMessage(thread_id=thread.id, role="manager", content=text, created_at=now)
        )
        db.add(
            AgentThreadMessage(
                thread_id=thread.id,
                role="assistant",
                content=reply,
                message_metadata=extra or {},
                created_at=now + timedelta(milliseconds=5),
            )
        )
        thread.updated_at = now
        db.commit()
        return {"handled": True}

    @classmethod
    def _handle_work_chat(cls, db: Session, thread: AgentThread, prism: Prism, text: str) -> dict:
        """A task becomes a plan card; questions about earlier work are answered from its results."""

        normalized = " ".join(text.split())
        if looks_like_task(db, prism.name, normalized):
            ok, reason = cls.available()
            if not ok:
                return cls._reply(
                    db, thread, text, reason or "My computer isn't available right now."
                )
            busy = db.scalar(
                select(QaRun).where(QaRun.prism_id == prism.id, QaRun.state.in_(QA_ACTIVE_STATES))
            )
            if busy is not None:
                title = (busy.plan or {}).get("title") or "another task"
                return cls._reply(
                    db,
                    thread,
                    text,
                    f"I'm still working on “{title}”. Want me to stop that first, or wait until I'm done?",
                    {"kind": "work_busy", "qa_run_id": str(busy.id)},
                )
            try:
                plan = WorkPlanService.build(db, prism=prism, thread_id=thread.id, text=text)
            except QaPlanError as exc:
                return cls._reply(db, thread, text, str(exc))
            run = QaRun(
                prism_id=prism.id, thread_id=thread.id, kind="work", state="planned", plan=plan
            )
            db.add(run)
            db.flush()
            now = _now()
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id, role="manager", content=text, created_at=now
                )
            )
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id,
                    role="assistant",
                    content="Here's how I'd do it. Start me when you're happy with it.",
                    message_metadata={"kind": "work_plan", "qa_run_id": str(run.id)},
                    created_at=now + timedelta(milliseconds=5),
                )
            )
            thread.updated_at = now
            db.commit()
            return {"handled": True, "qa_run_id": run.id}
        has_work = db.scalar(
            select(QaRun.id).where(QaRun.prism_id == prism.id, QaRun.state != "planned").limit(1)
        )
        if has_work is None:
            return {"handled": False}
        return cls._follow_up(db, thread, prism, text)

    # ---------- chat: follow-up questions about the tests ----------

    @classmethod
    def _follow_up(cls, db: Session, thread: AgentThread, prism: Prism, text: str) -> dict:
        """Answer from the Prism's own test results. Teams is read only when the manager asks about it."""

        from app.services.chat_intent_service import _names_a_person

        normalized = " ".join(text.split())
        about_mine = bool(_MY_RESULTS.search(normalized)) and prism.template_key != "qa_tester"
        if _TEAMS_INTENT.search(normalized) and not about_mine:
            return {"handled": False}
        # Naming a colleague is about Teams unless it is about my results ("write this up for Akshay").
        if _names_a_person(db, normalized) and not _ABOUT_MY_WORK.search(normalized):
            return {"handled": False}
        runs = list(
            db.scalars(
                select(QaRun)
                .where(QaRun.prism_id == prism.id, QaRun.state != "planned")
                .order_by(QaRun.created_at.desc())
                .limit(4)
            )
        )
        answered = cls._answer(db, thread, prism, normalized, runs)
        if answered is None:
            return {"handled": False}
        reply, draft = answered
        now = _now()
        if draft and cls._draft_card(db, thread, prism, text, reply, draft, now):
            return {"handled": True}
        if draft:
            # No Teams chat with that person: keep the text so it can still be copied.
            reply += f"\n\nI couldn't find a Teams chat or group with {draft['to']} that I can use, so I can't make a sendable draft. Here's the message:\n{draft['body']}"
        db.add(
            AgentThreadMessage(thread_id=thread.id, role="manager", content=text, created_at=now)
        )
        db.add(
            AgentThreadMessage(
                thread_id=thread.id,
                role="assistant",
                content=reply,
                created_at=now + timedelta(milliseconds=5),
            )
        )
        thread.updated_at = now
        db.commit()
        return {"handled": True}

    @classmethod
    def _results_context(cls, runs: list[QaRun]) -> list[dict]:
        out = []
        for run in runs:
            report = run.report or {}
            if run.kind == "work":
                out.append(
                    {
                        "task": (run.plan or {}).get("title"),
                        "state": run.state,
                        "when": run.ended_at.isoformat() if run.ended_at else None,
                        "summary": report.get("summary"),
                        "results": (report.get("rows") or [])[:30],
                        "files": [f.get("name") for f in report.get("files", [])],
                        "needs_attention": report.get("needs_attention", []),
                    }
                )
                continue
            out.append(
                {
                    "site": (run.plan or {}).get("host"),
                    "state": run.state,
                    "when": run.ended_at.isoformat() if run.ended_at else None,
                    "counts": report.get("counts")
                    or {k: v for k, v in (run.cases or {}).items() if k != "synced_at"},
                    "failed_or_blocked_checks": [
                        {"title": c["title"], "status": c["status"], "notes": c.get("notes", "")}
                        for c in report.get("cases", [])
                        if c.get("status") in ("fail", "blocked")
                    ][:12],
                    "issues": [
                        {k: b.get(k) for k in ("title", "severity", "steps", "expected", "actual")}
                        for b in report.get("bugs", [])
                    ][:12],
                    "summary": report.get("summary"),
                }
            )
        return out

    @classmethod
    def _answer(
        cls, db: Session, thread: AgentThread, prism: Prism, text: str, runs: list[QaRun]
    ) -> tuple[str, dict | None] | None:
        """(reply, optional draft) or None to leave the message to the normal chat."""

        from app.models.prism_v22 import PrismWorkingAgreement
        from app.services.agent_preference_service import AgentPreferenceService
        from app.services.llm_service import LLMService
        from app.services.people_directory_service import PeopleDirectoryService

        results = cls._results_context(runs)
        try:
            agreement = db.scalar(
                select(PrismWorkingAgreement)
                .where(PrismWorkingAgreement.prism_id == prism.id)
                .order_by(PrismWorkingAgreement.revision.desc())
            )
            recent = list(
                db.scalars(
                    select(AgentThreadMessage)
                    .where(
                        AgentThreadMessage.thread_id == thread.id,
                        AgentThreadMessage.job_id.is_(None),
                    )
                    .order_by(AgentThreadMessage.created_at.desc())
                    .limit(6)
                )
            )[::-1]
            work = prism.template_key != "qa_tester"
            prompt = (
                WORK_FOLLOW_UP_PROMPT.format(
                    name=prism.name, description=prism.description[:400], draft_rule=DRAFT_RULE
                )
                if work
                else FOLLOW_UP_PROMPT.format(name=prism.name, draft_rule=DRAFT_RULE)
            )
            answer = LLMService.complete(
                prompt=prompt,
                context={
                    "message": text,
                    "about_the_manager": PeopleDirectoryService.manager_context(db),
                    "about_the_organisation": BrainService.context(db),
                    "working_agreement": agreement.agreement if agreement else None,
                    "manager_instructions": [
                        i.instruction
                        for i in AgentPreferenceService.active(db, thread_id=thread.id)
                    ],
                    "my_work_results" if work else "my_test_results": results,
                    "test_running_now": any(r.state in QA_ACTIVE_STATES for r in runs),
                    "recent_conversation": [
                        {
                            "from": "manager" if m.role == "manager" else prism.name,
                            "text": m.content[:400],
                        }
                        for m in recent
                    ],
                },
                output_model=_Answer,
                feature="prism_qa_followup",
            )
            if answer.needs_other_help:
                return None
            draft = None
            if answer.draft_body.strip() and answer.draft_to.strip():
                draft = {"to": answer.draft_to.strip(), "body": answer.draft_body.strip()}
            reply = answer.reply.strip()
            if reply or draft:
                return reply or "Here's the draft.", draft
        except Exception:  # noqa: BLE001 - the plain answer below is always safe
            logger.info("qa_followup_model_unavailable", exc_info=False)
        if not _ABOUT_RESULTS.search(text):
            return None
        if prism.template_key != "qa_tester":
            return cls._plain_work_answer(results), None
        return cls._plain_answer(results, text)

    @staticmethod
    def _plain_work_answer(results: list[dict]) -> str:
        done = next(
            (r for r in results if r["state"] in ("succeeded", "failed", "timed_out")), None
        )
        if done is None:
            return (
                "I'm still working, so I don't have results yet. I'll bring them here as soon as I'm done."
                if results
                else "I haven't done any work yet. Give me a task and I'll show you a plan first."
            )
        found = len(done.get("results") or [])
        text = f"From my last task, “{done['task']}”: {done.get('summary') or 'I have no summary.'}"
        if found:
            text += f" I found {found} item{'s' if found != 1 else ''}; they're in my report above."
        return text

    @staticmethod
    def _plain_answer(results: list[dict], text: str = "") -> tuple[str, dict | None]:
        done = next(
            (r for r in results if r["state"] in ("succeeded", "failed", "timed_out")), None
        )
        if done is None:
            if results:
                return (
                    "I'm still testing, so I don't have results to go on yet. I'll bring them here as soon as I'm done.",
                    None,
                )
            return (
                "I haven't tested anything yet. Send me a site and what to check, and I'll show you a plan first.",
                None,
            )
        lines = [f"From my last test of {done['site']}, here's what I'd focus on:"]
        for issue in done["issues"]:
            detail = issue.get("actual") or issue.get("expected") or ""
            lines.append(
                f"- {issue['title']} ({issue.get('severity', 'medium')}){': ' + detail if detail else ''}"
            )
        listed = {i["title"] for i in done["issues"]}
        for check in done["failed_or_blocked_checks"]:
            if check["title"] not in listed:
                note = f": {check['notes']}" if check["notes"] else ""
                lines.append(
                    f"- {check['title']} ({'failed' if check['status'] == 'fail' else 'could not check'}){note}"
                )
        if len(lines) == 1:
            lines.append(
                "Nothing failed, so there's nothing urgent. I can test more pages or deeper cases if you like."
            )
        draft = None
        if re.search(r"\bdraft\b", text, re.I):
            who = re.search(r"\b(?:to|for)\s+([A-Za-z][\w'-]*)\s*$", text.strip().rstrip(".!?"))
            body = (
                "\n".join(line for line in lines[1:] if line.startswith("- "))
                or "- Nothing failed."
            )
            name = who.group(1).title() if who else ""
            draft = {
                "to": name,
                "body": f"Hi{' ' + name if name else ''},\nI tested {done['site']} and found a few things to look at:\n{body}\nCould you take a look when you get a chance?",
            }
        return "\n".join(lines), draft

    # ---------- chat: a draft message as a real draft card ----------

    @staticmethod
    def _recipients(name: str) -> list[str]:
        parts = re.split(r"\s*(?:,|&|\band\b)\s*", name.strip(), flags=re.I)
        return [part.strip() for part in parts if len(part.strip()) >= 2]

    @classmethod
    def _find_chat(cls, db: Session, prism: Prism, name: str, hint: str = ""):
        """The Teams chat this Prism may use for that person, those people, or that group, or None.

        One person: their most recent 1:1 chat. Several people, or a group the manager mentions: the
        smallest group chat that has all of them (or is named as such).
        """

        from app.services.prism_teams_policy_service import PrismTeamsPolicyService

        wanted = [token.casefold() for token in cls._recipients(name)]
        if not wanted:
            return None
        try:
            _, catalog = PrismTeamsPolicyService.allowed_sources(db, prism.id)
        except Exception:  # noqa: BLE001 - no Teams connection means no card, not a failure
            logger.info("qa_draft_teams_unavailable", exc_info=False)
            return None

        def covers(source, token: str) -> bool:
            names = [source.label, *source.participants]
            return any(
                token in str(n).casefold().split() or str(n).casefold().startswith(token)
                for n in names
            )

        def newest(sources):
            return sorted(
                sources,
                key=lambda s: s.last_updated_at.timestamp() if s.last_updated_at else 0,
                reverse=True,
            )

        as_group = len(wanted) > 1 or bool(re.search(r"\bgroup\b", f"{name} {hint}", re.I))
        if not as_group:
            found = newest(s for s in catalog if s.chat_type == "private" and covers(s, wanted[0]))
            return found[0] if found else None
        groups = [
            s for s in catalog if s.chat_type == "group" and all(covers(s, t) for t in wanted)
        ]
        if not groups and len(wanted) == 1:
            # "our group" with one name or a group's own name: any group that matches it
            groups = [s for s in catalog if s.chat_type == "group" and covers(s, wanted[0])]
        groups = newest(groups)
        groups.sort(
            key=lambda s: len(s.participants or [])
        )  # the closest fit, newest first on ties
        return groups[0] if groups else None

    @classmethod
    def _draft_card(
        cls,
        db: Session,
        thread: AgentThread,
        prism: Prism,
        text: str,
        summary: str,
        draft: dict,
        now,
        echo: bool = True,
    ) -> bool:
        """Store the draft as a pending Teams draft the manager can edit, approve and send."""

        chat = cls._find_chat(db, prism, draft["to"], text)
        if chat is None:
            return False
        try:
            return cls._store_draft(db, thread, text, summary, draft, chat, now, echo)
        except Exception:  # noqa: BLE001 - fall back to showing the text rather than failing the chat
            db.rollback()
            logger.exception("qa_draft_card_failed")
            return False

    @classmethod
    def _store_draft(
        cls,
        db: Session,
        thread: AgentThread,
        text: str,
        summary: str,
        draft: dict,
        chat,
        now,
        echo: bool = True,
    ) -> bool:
        from app.models.agent_v21 import AgentConversationReview
        from app.models.enums import AgentJobState
        from app.services.agent_state_service import AgentStateService

        job = AgentStateService.create_job(
            db,
            thread_id=thread.id,
            goal=text,
            scope_mode="person",
            requested_scope={
                "source_kind": "teams_chat",
                "external_id": chat.external_id,
                "label": chat.label,
                "retrieved_source_count": 0,
                "qa_draft": True,
            },
            resolved_sources=[
                {
                    "kind": "teams_chat",
                    "external_id": chat.external_id,
                    "label": chat.label,
                    "metadata": {"chat_type": chat.chat_type, "participants": chat.participants},
                    "selection_reason": "destination",
                }
            ],
        )
        for target in (AgentJobState.RESEARCHING, AgentJobState.PLANNING):
            job = AgentStateService.transition_job(
                db, job.id, target=target, expected_version=job.version
            )
        db.add(
            AgentConversationReview(
                job_id=job.id,
                summary=summary[:3000],
                summary_evidence_ids=[],
                attention_items=[],
                manager_questions=[],
                requires_reply=True,
                proposed_reply={
                    "body": draft["body"][:4000],
                    "reason": "Written from my test results. It is not based on Teams messages.",
                    "evidence_ids": [],
                },
                confidence=0.9,
                limitations=["This draft is based on my test results, not on Teams messages."],
                applied_preference_ids=[],
                provider="qa-tester",
                model="qa-tester",
            )
        )
        db.flush()
        AgentStateService.create_proposal(
            db,
            job_id=job.id,
            action="teams.send_chat_message",
            destination={
                "kind": "teams_chat",
                "chat_id": chat.external_id,
                "label": chat.label,
                "participants": chat.participants,
            },
            body=draft["body"][:4000],
            reason="Written from my test results. It is not based on Teams messages.",
            evidence_ids=[],
        )
        AgentStateService.transition_job(
            db, job.id, target=AgentJobState.WAITING_FOR_APPROVAL, expected_version=job.version
        )
        if echo:
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id, role="manager", content=text, job_id=job.id, created_at=now
                )
            )
        if summary and echo:
            db.add(
                AgentThreadMessage(
                    thread_id=thread.id,
                    role="assistant",
                    content=summary,
                    created_at=now + timedelta(milliseconds=5),
                )
            )
        db.add(
            AgentThreadMessage(
                thread_id=thread.id,
                role="assistant",
                content=summary or "Here's the draft.",
                job_id=job.id,
                message_metadata={"kind": "conversation_review"},
                created_at=now + timedelta(milliseconds=10),
            )
        )
        thread.updated_at = now
        db.commit()
        return True

    @staticmethod
    def _plan_intro(prism: Prism, plan: dict) -> str:
        where = plan["host"]
        extra = (
            " It's a live site, so I'll only look, never submit real data."
            if plan["environment"] == "production"
            else ""
        )
        return f"Here's how I'd test {where}.{extra} Start me when you're happy with it."

    # ---------- chat: messages ----------

    @staticmethod
    def _post(db: Session, run: QaRun, content: str, kind: str, extra: dict | None = None) -> None:
        thread = db.get(AgentThread, run.thread_id)
        db.add(
            AgentThreadMessage(
                thread_id=run.thread_id,
                role="assistant",
                content=content,
                message_metadata={"kind": kind, "qa_run_id": str(run.id), **(extra or {})},
                created_at=_now(),
            )
        )
        if thread is not None:
            thread.updated_at = _now()

    # ---------- lifecycle ----------

    @staticmethod
    def get(db: Session, qa_run_id: uuid.UUID, *, lock: bool = False) -> QaRun:
        query = select(QaRun).where(QaRun.id == qa_run_id)
        run = db.scalar(query.with_for_update() if lock else query)
        if run is None:
            raise NotFoundError("That test run was not found")
        return run

    @classmethod
    def start(cls, db: Session, qa_run_id: uuid.UUID, edits: dict | None = None) -> QaRun:
        run = cls.get(db, qa_run_id, lock=True)
        if run.state != "planned":
            raise RuleViolationError("That test has already been started")
        ok, reason = cls.available()
        if not ok:
            raise RuleViolationError(reason or "Testing isn't available right now")
        busy = db.scalar(
            select(QaRun.id).where(
                QaRun.prism_id == run.prism_id,
                QaRun.state.in_(QA_ACTIVE_STATES),
                QaRun.id != run.id,
            )
        )
        if busy is not None:
            raise RuleViolationError(
                "I'm already running a test. Let me finish or stop that one first."
            )
        work = run.kind == "work"
        run.plan = (
            WorkPlanService.apply_edits(run.plan, edits)
            if work
            else QaPlanService.apply_edits(run.plan, edits)
        )
        plan = run.plan
        run.state = "starting"
        run.started_at = _now()
        db.commit()
        try:
            with make_client() as client:
                prism = db.get(Prism, run.prism_id)
                if work or get_settings().prism_v24_enabled:
                    # The Prism's own agent and computer (role, tools and logins are its own).
                    agent_id = PrismAgentService.ensure(db, prism, client)
                else:
                    agent_id = client.agent_id()
                if work:
                    target_id = None
                    steps = "\n".join(f"- {step}" for step in plan["steps"])
                    goal = f"{plan['request']}\n\nPlan:\n{steps}"
                    scope = {
                        "steps": plan["steps"],
                        "allowed_origins": WorkPlanService.origins(plan),
                        "focus": plan.get("notes", ""),
                    }
                    pages: list[str] = []
                else:
                    target_id = client.find_or_create_target(
                        base_url=plan["site"],
                        name=plan["host"],
                        environment=plan["environment"],
                        notes=plan.get("notes", ""),
                        extra_origins=[],
                    )
                    goal = plan["request"]
                    scope = {
                        "urls": plan["pages"],
                        "features": plan["features"],
                        "acceptance_criteria": plan["acceptance_criteria"],
                        "allow_bug_filing": bool(plan["allow_bug_filing"]),
                        "focus": plan.get("notes", ""),
                    }
                    pages = plan["pages"] if plan["pages"] != ["/"] else []
                task_id = client.create_task(
                    title=plan["title"],
                    goal=goal,
                    agent_id=agent_id,
                    target_id=target_id,
                    scope=scope,
                )
                swarm_run = client.start_run(
                    task_id,
                    max_turns=int(plan["max_turns"]),
                    budget_usd=float(plan["budget_usd"]),
                    pages=pages,
                )
        except SwarmError as exc:
            cls._fail(db, run, str(exc))
            return run
        run = cls.get(db, qa_run_id, lock=True)
        run.swarm_target_id = target_id
        run.swarm_task_id = task_id
        run.swarm_run_id = swarm_run["id"]
        run.swarm_run_ids = [swarm_run["id"]]
        run.state = "running"
        run.cases = {"synced_at": _now().isoformat()}
        cls._post(db, run, "On it. You can watch my screen on the right.", "qa_started")
        db.commit()
        return run

    @classmethod
    def _fail(cls, db: Session, run: QaRun, message: str) -> None:
        db.rollback()
        run = cls.get(db, run.id, lock=True)
        run.state = "error"
        run.error = message
        run.ended_at = _now()
        what = "that task" if run.kind == "work" else "that test"
        cls._post(db, run, f"I couldn't run {what}. {message}", "qa_error")
        db.commit()

    @classmethod
    def cancel(cls, db: Session, qa_run_id: uuid.UUID) -> QaRun:
        run = cls.get(db, qa_run_id, lock=True)
        if run.state == "planned":
            run.state = "cancelled"
            run.ended_at = _now()
            db.commit()
            return run
        if run.state not in QA_ACTIVE_STATES:
            return run
        if run.swarm_run_id:
            try:
                with make_client() as client:
                    client.cancel(run.swarm_run_id)
            except SwarmError as exc:
                raise RuleViolationError(str(exc)) from exc
        run.state = "cancelled"
        run.ended_at = _now()
        run.current_activity = "Stopped"
        cls._post(
            db,
            run,
            "Okay, I've stopped." if run.kind == "work" else "Okay, I've stopped the test.",
            "qa_cancelled",
        )
        db.commit()
        return run

    # ---------- following a run ----------

    @classmethod
    def sync(
        cls, db: Session, qa_run_id: uuid.UUID, client: QaSwarmClient | None = None
    ) -> QaRun | None:
        """Pull new progress from the testing workspace. Skips if another worker holds the run."""

        run = db.scalar(
            select(QaRun).where(QaRun.id == qa_run_id).with_for_update(skip_locked=True)
        )
        if run is None or run.state not in QA_ACTIVE_STATES or not run.swarm_run_id:
            db.rollback()
            return run
        owned = client is None
        try:
            client = client or make_client()
            cls._sync_locked(db, run, client)
            run.cases = {**run.cases, "synced_at": _now().isoformat()}
        except SwarmError as exc:
            last_ok = _parse_time((run.cases or {}).get("synced_at")) or _aware(run.started_at)
            if last_ok and _now() - last_ok > OFFLINE_GRACE:
                run.state = "error"
                run.error = str(exc)
                run.ended_at = _now()
                cls._post(
                    db,
                    run,
                    "I lost contact with my testing workspace, so I had to stop. Try again in a bit.",
                    "qa_error",
                )
            else:
                run.current_activity = "Waiting for my testing workspace…"
        finally:
            if owned and client is not None:
                client.close()
        db.commit()
        return run

    @classmethod
    def _sync_locked(cls, db: Session, run: QaRun, client: QaSwarmClient) -> None:
        swarm_id = run.swarm_run_id
        swarm_run = client.run(swarm_id)
        events = client.events(swarm_id, run.last_event_seq)
        log = list(run.activity_log or [])
        screenshots = list(run.screenshot_ids or [])
        live = None
        for event in events:
            run.last_event_seq = max(run.last_event_seq, int(event["seq"]))
            payload = event.get("payload") or {}
            kind = event.get("type")
            if kind == "tool_call":
                args = (
                    payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
                )
                text = activity_text(str(payload.get("tool", "")), args)
                if payload.get("tool") == "browser_navigate" and args.get("url"):
                    run.current_url = str(args["url"])[:2048]
                run.current_activity = text[:300]
                run.turn += 1
                log.append({"at": event.get("created_at"), "text": text})
            elif kind == "checklist" and isinstance(payload.get("steps"), list):
                run.checklist = [
                    {
                        "title": str(step.get("title", ""))[:200],
                        "status": step.get("status")
                        if step.get("status") in ("todo", "doing", "done", "skipped")
                        else "todo",
                    }
                    for step in payload["steps"][:12]
                    if isinstance(step, dict)
                ]
            elif kind == "message" and payload.get("kind") == "comment" and run.kind == "work":
                log.append(
                    {"at": event.get("created_at"), "text": str(payload.get("text", ""))[:200]}
                )
            elif kind == "artifact" and payload.get("kind") == "frame":
                if payload.get("artifact_id"):
                    run.latest_frame_id = payload["artifact_id"]
                    run.frame_count = (run.frame_count or 0) + 1
            elif kind == "usage" and payload.get("cost_usd") is not None:
                # The workspace saves a run's cost only when the run ends; usage events carry it live.
                live = payload["cost_usd"]
            elif kind == "artifact" and payload.get("kind") == "screenshot":
                artifact_id = payload.get("artifact_id")
                if artifact_id and artifact_id not in screenshots:
                    screenshots.append(artifact_id)
                    run.latest_screenshot_id = artifact_id
        run.activity_log = log[-LOG_LIMIT:]
        run.screenshot_ids = screenshots[:500]
        if live is not None:
            run.cases = {**(run.cases or {}), "cost_live": float(live), "cost_live_run": swarm_id}
        cls._refresh_cost(run, swarm_run)
        if run.kind == "qa":
            cls._refresh_cases(run, client)

        status = swarm_run.get("status")
        if status == "waiting_approval":
            cls._relay_approvals(db, run, client)
            run.state = "waiting_approval"
            run.current_activity = "Waiting for your approval"
        elif status in ("queued", "running", "waiting_children"):
            if run.state == "waiting_approval" and not cls._pending(db, run):
                run.state = "running"
            elif run.state == "starting":
                run.state = "running"
        elif status in _SWARM_TERMINAL:
            cls._finish(db, run, client, swarm_run, _STATE_FOR[status])

    @staticmethod
    def _refresh_cost(run: QaRun, swarm_run: dict) -> None:
        current = swarm_run.get("total_cost_usd")
        if current is None:
            current = swarm_run.get("cost_usd") or 0
        cases = run.cases or {}
        current = Decimal(str(current))
        if cases.get("cost_live_run") == swarm_run.get("id", run.swarm_run_id):
            current = max(current, Decimal(str(cases.get("cost_live", 0))))
        prior = Decimal(str(cases.get("cost_prior", 0)))
        run.cost_usd = prior + current

    @classmethod
    def _all_cases(cls, run: QaRun, client: QaSwarmClient) -> list[dict]:
        seen: dict[str, dict] = {}
        for swarm_id in run.swarm_run_ids or []:
            for case in client.test_cases(swarm_id):
                seen[case["id"]] = case
        return list(seen.values())

    @classmethod
    def _refresh_cases(cls, run: QaRun, client: QaSwarmClient) -> None:
        cases = cls._all_cases(run, client)
        counts = {"total": len(cases), "pass": 0, "fail": 0, "blocked": 0, "skipped": 0}
        for case in cases:
            if case.get("status") in counts:
                counts[case["status"]] += 1
        run.cases = {**(run.cases or {}), **counts}

    # ---------- approvals ----------

    @staticmethod
    def _pending(db: Session, run: QaRun) -> list[QaApproval]:
        return list(
            db.scalars(
                select(QaApproval).where(
                    QaApproval.qa_run_id == run.id, QaApproval.status == "pending"
                )
            )
        )

    @classmethod
    def _relay_approvals(cls, db: Session, run: QaRun, client: QaSwarmClient) -> None:
        known = {
            row.swarm_approval_id
            for row in db.scalars(select(QaApproval).where(QaApproval.qa_run_id == run.id))
        }
        bugs: dict[str, dict] = {}
        if run.kind == "qa":
            for swarm_id in run.swarm_run_ids or []:
                for bug in client.bugs(swarm_id):
                    bugs[bug["id"]] = bug
        for item in client.approvals():
            if (
                item.get("status") != "pending"
                or item.get("run_id") != run.swarm_run_id
                or item["id"] in known
            ):
                continue
            action = item.get("action", "")
            args = (item.get("payload") or {}).get("arguments") or {}
            kind, payload, message = cls._approval_view(run, action, args, bugs)
            approval = QaApproval(
                qa_run_id=run.id,
                swarm_approval_id=item["id"],
                action=action,
                kind=kind,
                payload=payload,
            )
            db.add(approval)
            db.flush()
            cls._post(
                db,
                run,
                message,
                "qa_approval" if kind == "bug_filing" else "work_approval",
                {"qa_approval_id": str(approval.id), "approval_kind": kind},
            )

    @classmethod
    def _approval_view(
        cls, run: QaRun, action: str, args: dict, bugs: dict[str, dict]
    ) -> tuple[str, dict, str]:
        """(kind, safe payload for the card, the chat line) for something the engine paused on."""

        if action == "file_bug":
            bug = bugs.get(str(args.get("bug_id") or ""))
            payload = cls._bug_view(bug, run) if bug else {"title": "A bug I found"}
            title = payload.get("title", "a bug")
            return (
                "bug_filing",
                payload,
                f"I found something worth filing: {title}. Want me to file it?",
            )
        if action == "ask_manager":
            question = str(args.get("question") or "I have a question.")[:500]
            return "question", {"question": question}, question
        if action == "request_login":
            site = str(args.get("site") or "a site")[:200]
            reason = str(args.get("reason") or "")[:300]
            text = f"I need to sign in to {site}." + (f" {reason}" if reason else "")
            return "login", {"site": site, "reason": reason}, text
        summary = str(args.get("summary") or "")[:300]
        site = str(args.get("site") or "")[:200]
        if action == "browser_click":
            summary = f"click “{str(args.get('element') or 'a button')[:120]}”"
            site = (run.current_url or "")[:200]
        details = str(args.get("details") or "")[:1500]
        payload = {
            "summary": summary or "do something that can't be undone",
            "site": site,
            "details": details,
            "frame": bool(run.latest_frame_id),
        }
        where = f" on {site}" if site else ""
        return (
            "outward_action",
            payload,
            f"I'm about to {payload['summary']}{where}. Want me to go ahead?",
        )

    @staticmethod
    def _bug_view(bug: dict, run: QaRun) -> dict:
        return {
            "title": bug.get("title", ""),
            "severity": bug.get("severity", "medium"),
            "steps": bug.get("steps", ""),
            "expected": bug.get("expected", ""),
            "actual": bug.get("actual", ""),
        }

    @classmethod
    def decide(
        cls,
        db: Session,
        approval_id: uuid.UUID,
        decision: str,
        comment: str = "",
        answer: str | None = None,
        login: dict | None = None,
    ) -> QaApproval:
        if decision not in ("approve", "reject"):
            raise RuleViolationError("Choose approve or reject")
        approval = db.scalar(
            select(QaApproval).where(QaApproval.id == approval_id).with_for_update()
        )
        if approval is None:
            raise NotFoundError("That approval was not found")
        if approval.status != "pending":
            return approval
        run = cls.get(db, approval.qa_run_id, lock=True)
        payload = None
        if decision == "approve" and approval.kind == "question":
            answer = " ".join((answer or "").split())[:1000]
            if not answer:
                raise RuleViolationError("Type your answer first")
            payload = {"answer": answer}
        if decision == "approve" and approval.kind == "login":
            login = login or {}
            if not str(login.get("username") or "").strip() or not str(login.get("password") or ""):
                raise RuleViolationError("Enter the username and password")
        try:
            with make_client() as client:
                if decision == "approve" and approval.kind == "login":
                    from app.services.prism_login_service import PrismLoginService

                    origin = PrismLoginService.store(
                        db,
                        db.get(Prism, run.prism_id),
                        client,
                        site=str(approval.payload.get("site") or ""),
                        username=str(login["username"]).strip(),
                        password=str(login["password"]),
                        remember=bool(login.get("remember", True)),
                    )
                    cls._note_from_manager(
                        db, run, f"You gave {cls._name(db, run)} a login for {origin}."
                    )
                result = client.decide(approval.swarm_approval_id, decision, comment[:500], payload)
                previous = run.swarm_run_id
                if previous:
                    swarm_run = client.run(previous)
                    prior = Decimal(str((run.cases or {}).get("cost_prior", 0)))
                    spent = swarm_run.get("total_cost_usd") or swarm_run.get("cost_usd") or 0
                    run.cases = {
                        **(run.cases or {}),
                        "cost_prior": float(prior + Decimal(str(spent))),
                    }
        except SwarmError as exc:
            raise RuleViolationError(str(exc)) from exc
        if payload and payload.get("answer"):
            cls._note_from_manager(db, run, payload["answer"])
        approval.status = "approved" if decision == "approve" else "rejected"
        approval.comment = comment[:500] or None
        approval.decided_at = _now()
        resume = result.get("resume_run_id")
        if resume:
            run.swarm_run_id = resume
            run.swarm_run_ids = [*(run.swarm_run_ids or []), resume]
            run.last_event_seq = 0
        if not cls._pending(db, run) or resume:
            run.state = "running"
            run.current_activity = "Carrying on"
        db.commit()
        return approval

    @staticmethod
    def _name(db: Session, run: QaRun) -> str:
        prism = db.get(Prism, run.prism_id)
        return prism.name if prism else "Prism"

    @staticmethod
    def _note_from_manager(db: Session, run: QaRun, content: str) -> None:
        """A line in the chat from the manager (an answer, or "you gave a login"). Never a secret."""

        db.add(
            AgentThreadMessage(
                thread_id=run.thread_id, role="manager", content=content, created_at=_now()
            )
        )

    # ---------- finishing ----------

    FRIENDLY_ERRORS = {
        "failed": "I ran into a problem before I could finish.",
        "cancelled": "The test was stopped.",
        "timed_out": "The test took longer than allowed, so it was stopped.",
    }

    @classmethod
    def _finish(
        cls, db: Session, run: QaRun, client: QaSwarmClient, swarm_run: dict, state: str
    ) -> None:
        run.state = state
        run.ended_at = _now()
        run.current_activity = {
            "succeeded": "Finished",
            "failed": "Stopped with a problem",
            "cancelled": "Stopped",
            "timed_out": "Ran out of time",
        }[state]
        # Raw errors from the testing workspace are never shown; the manager gets a plain sentence.
        run.error = None if state == "succeeded" else cls.FRIENDLY_ERRORS[state]
        screenshots = list(run.screenshot_ids or [])
        for swarm_id in run.swarm_run_ids or []:
            for art in client.artifacts(swarm_id):
                if art.get("kind") == "screenshot" and art["id"] not in screenshots:
                    screenshots.append(art["id"])
        run.screenshot_ids = screenshots[:500]
        if screenshots and not run.latest_screenshot_id:
            run.latest_screenshot_id = screenshots[-1]
        if run.kind == "work":
            report = cls._build_work_report(db, run, client, swarm_run)
            run.report = report
            cls._post(db, run, report["summary"], "work_report")
            from app.services.prism_login_service import PrismLoginService

            PrismLoginService.forget_once(db, db.get(Prism, run.prism_id), client)
            return
        report = cls._build_report(db, run, client, swarm_run)
        run.report = report
        cls._post(db, run, report["summary"], "qa_report")

    @classmethod
    def _build_report(cls, db: Session, run: QaRun, client: QaSwarmClient, swarm_run: dict) -> dict:
        plan = run.plan
        cases = [
            {
                "title": c.get("title", ""),
                "given": c.get("given", ""),
                "when": c.get("when", ""),
                "then": c.get("then", ""),
                "status": c.get("status", "pending"),
                "notes": c.get("notes", ""),
                "screenshot_ids": [str(i) for i in (c.get("evidence_artifact_ids") or [])],
            }
            for c in cls._all_cases(run, client)
        ]
        bugs_by_id: dict[str, dict] = {}
        for swarm_id in run.swarm_run_ids or []:
            for bug in client.bugs(swarm_id):
                bugs_by_id[bug["id"]] = bug
        case_shots = {c["title"]: c["screenshot_ids"] for c in cases}
        bugs = []
        for bug in bugs_by_id.values():
            view = cls._bug_view(bug, run)
            related = next((c for c in cases if c["title"] == bug.get("title")), None)
            view["screenshot_ids"] = (related or {}).get("screenshot_ids") or case_shots.get(
                bug.get("title", ""), []
            )
            view["status"] = bug.get("status", "draft")
            bugs.append(view)
        counts = {"total": len(cases), "pass": 0, "fail": 0, "blocked": 0, "skipped": 0}
        for case in cases:
            if case["status"] in counts:
                counts[case["status"]] += 1
        duration = None
        if run.started_at and run.ended_at:
            duration = int((_aware(run.ended_at) - _aware(run.started_at)).total_seconds())
        report = {
            "site": plan["host"],
            "environment": plan["environment"],
            "outcome": run.state,
            "pages": plan["pages"],
            "counts": counts,
            "cases": cases,
            "bugs": bugs,
            "duration_seconds": duration,
            "cost_usd": float(run.cost_usd),
            "turns": run.turn,
            "screenshot_ids": list(run.screenshot_ids or []),
            "summary": "",
        }
        report["summary"] = cls._summary(db, run, report, swarm_run)
        return report

    @classmethod
    def _build_work_report(
        cls, db: Session, run: QaRun, client: QaSwarmClient, swarm_run: dict
    ) -> dict:
        result = swarm_run.get("result") or {}
        rows = [r for r in (result.get("results") or []) if isinstance(r, dict)]
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        files = [f for f in (result.get("files") or []) if f.get("artifact_id")]
        run.file_ids = [f["artifact_id"] for f in files][:20]
        duration = None
        if run.started_at and run.ended_at:
            duration = int((_aware(run.ended_at) - _aware(run.started_at)).total_seconds())
        report = {
            "kind": "work",
            "title": (run.plan or {}).get("title"),
            "outcome": run.state,
            "task_outcome": result.get("outcome"),
            "columns": columns[:8],
            "rows": rows[:100],
            "row_count": len(rows),
            "files": [
                {"name": str(f.get("name", "file"))[:120], "index": i}
                for i, f in enumerate(files[:20])
            ],
            "steps": list(run.checklist or []),
            "duration_seconds": duration,
            "cost_usd": float(run.cost_usd),
            "turns": run.turn,
            "summary": "",
            "needs_attention": [],
            "next_steps": [],
        }
        cls._work_summary(db, run, report, swarm_run)
        return report

    @staticmethod
    def _work_summary(db: Session, run: QaRun, report: dict, swarm_run: dict) -> None:
        from app.services.llm_service import LLMService

        prism = db.get(Prism, run.prism_id)
        title = report["title"] or "that task"
        if run.state == "succeeded":
            fallback = str(swarm_run.get("summary") or "").strip()[:700] or f"I finished “{title}”."
            if report["row_count"]:
                fallback += (
                    f" I found {report['row_count']} item{'s' if report['row_count'] != 1 else ''}."
                )
        else:
            fallback = (
                f"I couldn't finish “{title}”: {run.error or 'it stopped early'} "
                "Nothing was sent or changed on your behalf. Want me to try again?"
            )
        report["summary"] = fallback
        try:
            result = LLMService.complete(
                prompt=WORK_SUMMARY_PROMPT.format(name=prism.name if prism else "Prism"),
                context={
                    "task": title,
                    "outcome": run.state,
                    "found_count": report["row_count"],
                    "sample_results": report["rows"][:5],
                    "files": [f["name"] for f in report["files"]],
                    **(
                        {"agent_summary": str(swarm_run.get("summary") or "")[:1200]}
                        if run.state == "succeeded"
                        else {}
                    ),
                    "issue": run.error,
                    "about_the_organisation": BrainService.context(db),
                    "manager_instructions": [
                        i.instruction
                        for i in AgentPreferenceService.active(db, thread_id=run.thread_id)
                    ],
                },
                output_model=_WorkSummary,
                feature="prism_work_report",
            )
            report["summary"] = result.summary.strip() or fallback
            report["needs_attention"] = [
                x.strip()[:200] for x in result.needs_attention if x.strip()
            ][:4]
            report["next_steps"] = [x.strip()[:200] for x in result.next_steps if x.strip()][:3]
        except Exception:  # noqa: BLE001 - the plain summary is always good enough
            logger.info("work_summary_model_unavailable", exc_info=False)
        if prism is not None and run.state == "succeeded":
            try:
                BrainService.note_work(db, prism, title, report["summary"])
            except Exception:  # noqa: BLE001 - the shared note is a bonus
                db.rollback()
                logger.info("brain_note_failed", exc_info=False)

    @staticmethod
    def _summary(db: Session, run: QaRun, report: dict, swarm_run: dict) -> str:
        from app.services.llm_service import LLMService

        prism = db.get(Prism, run.prism_id)
        c = report["counts"]
        if run.state == "succeeded":
            fallback = (
                f"I finished testing {report['site']}. {c['pass']} of {c['total']} checks passed"
            )
            if c["fail"]:
                fallback += f", {c['fail']} failed"
            if c["blocked"]:
                fallback += f", {c['blocked']} could not be checked"
            fallback += "."
        elif c["total"] == 0:
            fallback = (
                f"I couldn't test {report['site']}: {run.error or 'the test stopped early'} "
                "I didn't get to check anything, and nothing on your site was changed. Want me to try again?"
            )
        else:
            fallback = (
                f"My test of {report['site']} didn't finish ({run.state.replace('_', ' ')}). "
                f"I got through {c['total']} checks before it stopped."
            )
        if report["bugs"]:
            fallback += (
                f" I found {len(report['bugs'])} issue{'s' if len(report['bugs']) != 1 else ''}."
            )
        try:
            result = LLMService.complete(
                prompt=SUMMARY_PROMPT.format(name=prism.name if prism else "Prism"),
                context={
                    "site": report["site"],
                    "outcome": run.state,
                    "counts": c,
                    "failed_checks": [x["title"] for x in report["cases"] if x["status"] == "fail"][
                        :8
                    ],
                    "bugs": [
                        {"title": b["title"], "severity": b["severity"]} for b in report["bugs"]
                    ][:8],
                    **(
                        {"agent_summary": str(swarm_run.get("summary") or "")[:1200]}
                        if run.state == "succeeded"
                        else {}
                    ),
                    "issue": run.error,
                },
                output_model=_Summary,
                feature="prism_qa_report",
            )
            return result.summary.strip() or fallback
        except Exception:  # noqa: BLE001 - the template summary is always good enough
            logger.info("qa_summary_model_unavailable", exc_info=False)
            return fallback

    # ---------- watcher ----------

    @classmethod
    def cycle(cls, db: Session) -> int:
        """Follow every active run once. Safe to run from several processes."""

        ids = list(db.scalars(select(QaRun.id).where(QaRun.state.in_(QA_ACTIVE_STATES))))
        if not ids:
            return 0
        followed = 0
        try:
            client = make_client()
        except SwarmError:
            return 0
        try:
            for run_id in ids:
                try:
                    if cls.sync(db, run_id, client) is not None:
                        followed += 1
                except Exception:  # noqa: BLE001 - one run must never stop the others
                    db.rollback()
                    logger.exception("qa_run_sync_failed")
        finally:
            client.close()
        return followed

    # ---------- views (nothing here ever names the testing workspace) ----------

    @staticmethod
    def _screen_index(run: QaRun, artifact_id: str | None) -> int | None:
        ids = list(run.screenshot_ids or [])
        return ids.index(artifact_id) if artifact_id in ids else None

    @classmethod
    def _report_view(cls, run: QaRun) -> dict | None:
        """The stored report with testing-workspace ids replaced by plain screen numbers."""

        if not run.report:
            return None
        if run.report.get("kind") == "work":
            return dict(run.report)
        report = dict(run.report)
        ids = list(run.screenshot_ids or [])

        def screens(values: list[str]) -> list[int]:
            return [ids.index(v) for v in values if v in ids]

        report["screens"] = screens(report.pop("screenshot_ids", []))
        report["cases"] = [
            {
                **{k: v for k, v in c.items() if k != "screenshot_ids"},
                "screens": screens(c.get("screenshot_ids") or []),
            }
            for c in report.get("cases", [])
        ]
        report["bugs"] = [
            {
                **{k: v for k, v in b.items() if k != "screenshot_ids"},
                "screens": screens(b.get("screenshot_ids") or []),
            }
            for b in report.get("bugs", [])
        ]
        return report

    @classmethod
    def snapshot(cls, db: Session, run: QaRun) -> dict:
        pending = [
            {
                "id": str(a.id),
                "kind": a.kind,
                "view": {
                    k: v
                    for k, v in a.payload.items()
                    if k in ("question", "site", "reason", "summary", "details", "frame")
                },
                "title": a.payload.get("title", ""),
                "severity": a.payload.get("severity", ""),
                "steps": a.payload.get("steps", ""),
                "expected": a.payload.get("expected", ""),
                "actual": a.payload.get("actual", ""),
                "status": a.status,
            }
            for a in db.scalars(select(QaApproval).where(QaApproval.qa_run_id == run.id))
        ]
        plan = run.plan or {}
        cases = {
            k: v
            for k, v in (run.cases or {}).items()
            if k in ("total", "pass", "fail", "blocked", "skipped")
        }
        return {
            "id": str(run.id),
            "prism_id": str(run.prism_id),
            "state": run.state,
            "active": run.state in QA_ACTIVE_STATES,
            "site": plan.get("host"),
            "environment": plan.get("environment"),
            "kind": run.kind,
            "plan": {
                key: plan.get(key)
                for key in (
                    (
                        "title",
                        "steps",
                        "sites",
                        "any_public_site",
                        "uses",
                        "asks_first",
                        "max_turns",
                        "budget_usd",
                        "max_minutes",
                    )
                    if run.kind == "work"
                    else (
                        "title",
                        "pages",
                        "features",
                        "acceptance_criteria",
                        "max_turns",
                        "budget_usd",
                        "allow_bug_filing",
                        "may_file_bugs",
                        "environment",
                        "host",
                    )
                )
            },
            "checklist": list(run.checklist or []),
            "frame": run.frame_count if run.latest_frame_id else None,
            "current_url": run.current_url,
            "activity": run.current_activity,
            "activity_log": list(run.activity_log or [])[-20:],
            "screen": cls._screen_index(run, run.latest_screenshot_id),
            "cases": cases,
            "turn": run.turn,
            "max_turns": plan.get("max_turns"),
            "cost_usd": float(run.cost_usd),
            "budget_usd": plan.get("budget_usd"),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "error": run.error if run.state in ("error",) else None,
            "approvals": pending,
            "report": cls._report_view(run),
        }

    @classmethod
    def latest_frame(cls, db: Session, qa_run_id: uuid.UUID) -> tuple[bytes, str]:
        run = cls.get(db, qa_run_id)
        if not run.latest_frame_id:
            raise NotFoundError("There is no screen yet")
        try:
            with make_client() as client:
                return client.artifact_file(run.latest_frame_id)
        except SwarmError as exc:
            raise NotFoundError("The screen isn't available right now") from exc

    @classmethod
    def file(cls, db: Session, qa_run_id: uuid.UUID, index: int) -> tuple[bytes, str, str]:
        run = cls.get(db, qa_run_id)
        ids = list(run.file_ids or [])
        files = (run.report or {}).get("files") or []
        if index < 0 or index >= len(ids) or index >= len(files):
            raise NotFoundError("That file was not found")
        try:
            with make_client() as client:
                data, content_type = client.artifact_file(ids[index])
        except SwarmError as exc:
            raise NotFoundError("That file isn't available right now") from exc
        return data, content_type, str(files[index].get("name") or "file")

    @classmethod
    def artifact(cls, db: Session, qa_run_id: uuid.UUID, index: int) -> tuple[bytes, str]:
        run = cls.get(db, qa_run_id)
        ids = list(run.screenshot_ids or [])
        if index < 0 or index >= len(ids):
            raise NotFoundError("That screenshot was not found")
        try:
            with make_client() as client:
                return client.artifact_file(ids[index])
        except SwarmError as exc:
            raise NotFoundError("That screenshot isn't available right now") from exc
