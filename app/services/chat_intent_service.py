from __future__ import annotations

import logging
import re
import uuid
import zlib

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Messages that clearly ask for work skip the extra model call entirely, so they are never delayed
# or swallowed by the chat shortcut.
_WORK_WORDS = re.compile(
    r"\b(summar\w*|draft|send|reply|respond|review|check|chats?|messages?|teams|update[sd]?|"
    r"blockers?|escalat\w*|commitments?|follow[ -]?up|remind\w*|report|status|recap|digest|"
    r"deadline|approve|approval|schedule|meeting|task|ticket|incident|deploy\w*|releas\w*|ship\w*|"
    r"merge\w*|fix\w*|build|bug|page|pr|done|finish\w*|complete\w*|progress|working on|"
    r"ready|launch\w*|test\w*|issue|project|team|who|where|when|why|how long|eta|stuck|"
    r"blocked|delay\w*|late|ask|tell|notify|share|forward|follow)\b",
    re.I,
)

CHAT_PROMPT = """You are {name}, a person on the manager's team, in this role: {role}
You are chatting privately with the manager, the way a trusted colleague would. Sound like a real
person: warm, natural, brief, and in your own voice. No bullet points, no headings, no sign-offs, no
canned phrases such as "How can I assist you" or "As an AI". Match the manager's mood and length; a
greeting gets a greeting, a joke can get a light reply, a personal remark gets a human answer.
You know who the manager is (about_the_manager) and the people around them (people_you_know). Use
the manager's first name naturally now and then, not in every message, and use what you know about
roles and reporting lines when it helps. Never guess a role that is not listed.
Stay in your role: talk about your work and your area the way someone in that role would, and follow
the working agreement and the manager's instructions about tone and behaviour.
Never invent facts about the manager's team, people, chats, or work, and never say you read, sent,
checked, or changed anything. If you are sincerely asked whether you are an AI, say so plainly and
keep being helpful. Do not claim a body, a home, or experiences you cannot have; stay light instead.
Decide whether the message needs you to look at the manager's Teams chats, people, or work status, or
to draft or send anything. Anything that asks about a person, a task, a project, a page, a release, a
deadline, or what someone did or is doing needs a lookup: set needs_work_lookup to true and leave
reply empty. Only plain conversation (greetings, thanks, banter, how you are, what you can do) is
answered here; when unsure, set needs_work_lookup to true. Your reply is one to three plain sentences
spoken to the manager. It is never a message to someone else, and never repeats or continues a
draft. Otherwise set needs_work_lookup to false and write your reply. Return only the required structured result."""


_ABOUT_YOU = re.compile(r"\b(you|your|yours|you're|u)\b", re.I)
_GREETS_SOMEONE = re.compile(r"^\s*(?i:hi|hello|hey|dear)\s+([A-Z][a-z]+)\b")


def _names_a_person(db: Session, text: str) -> bool:
    """True when the message mentions anyone the manager works with, so it is about work."""

    from app.models.employee import Employee

    words = {part.lower() for part in re.findall(r"[A-Za-z]{3,}", text)}
    if not words:
        return False
    for (name,) in db.execute(select(Employee.name).where(Employee.is_active.is_(True))):
        if words & {part.lower() for part in re.findall(r"[A-Za-z]{3,}", name or "")}:
            return True
    return False


class ChatDecision(BaseModel):
    needs_work_lookup: bool
    reply: str = Field(default="", max_length=1200)


# Messages that are only small talk. Anything that might be about the manager's work falls through
# and is answered from Teams as before, so a real question is never swallowed by this shortcut.
_GREETING = re.compile(
    r"^(hi|hii+|hello|hey|heya|hiya|yo|sup|namaste|good\s+(morning|afternoon|evening|night))"
    r"(\s+(there|prism|team|again|buddy))?[\s!.,?]*$",
    re.I,
)
_THANKS = re.compile(
    r"^(thanks|thank\s+you|thx|ty|cheers|great|perfect|awesome|nice|cool|ok|okay|k|got\s+it|"
    r"sounds\s+good|alright|noted|good|fine|sure|understood)"
    r"(\s+(so\s+much|a\s+lot|prism|thanks|for\s+that|for\s+the\s+help))?[\s!.,]*$",
    re.I,
)
_HOW_ARE_YOU = re.compile(
    r"^(how\s+are\s+you|how'?s\s+it\s+going|how\s+do\s+you\s+do|what'?s\s+up|wassup)[\s!.,?]*$",
    re.I,
)
_IDENTITY = re.compile(
    r"^(who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|what'?s\s+your\s+name|"
    r"what\s+do\s+you\s+do|what\s+can\s+you\s+do|how\s+can\s+you\s+help(\s+me)?|help)[\s!.,?]*$",
    re.I,
)
_BYE = re.compile(
    r"^(bye|goodbye|good\s*night|see\s+you(\s+later)?|cya|talk\s+later)[\s!.,]*$", re.I
)

_VARIANTS = {
    "greeting": [
        "Hey! What can I help you with?",
        "Hi! What's on your mind?",
        "Hello! What do you need?",
    ],
    "thanks": ["Anytime.", "Happy to help.", "You got it."],
    "how_are_you": [
        "Doing well, thanks! What can I do for you?",
        "All good here. What do you need?",
    ],
    "bye": ["Talk soon!", "See you. I'll be here if anything comes up."],
}


class ChatIntentService:
    @staticmethod
    def reply(text: str, *, prism_name: str | None, prism_description: str | None) -> str | None:
        """A human reply when the message needs no Teams reading, otherwise None."""

        normalized = " ".join(text.split())
        if not normalized or len(normalized) > 60:
            return None
        pick = zlib.crc32(normalized.lower().encode())
        if _HOW_ARE_YOU.match(normalized):
            kind = "how_are_you"
        elif _GREETING.match(normalized):
            kind = "greeting"
        elif _THANKS.match(normalized):
            kind = "thanks"
        elif _BYE.match(normalized):
            kind = "bye"
        elif _IDENTITY.match(normalized):
            name = prism_name or "Prism"
            about = (prism_description or "").strip().rstrip(".")
            lead = f"I'm {name}" + (f". {about}." if about else ".")
            return (
                f"{lead} Ask me about anything happening in your Teams chats and "
                "I'll take a look. I only read them when you ask."
            )
        else:
            return None
        options = _VARIANTS[kind]
        return options[pick % len(options)]

    @staticmethod
    def respond(
        db: Session,
        *,
        thread_id: uuid.UUID,
        prism_id: uuid.UUID | None,
        text: str,
    ) -> str | None:
        """An in-character reply when the message needs no Teams reading, otherwise None.

        The model decides and writes the reply as the Prism. If it is unavailable or returns
        something unusable, only the simple, safe small-talk replies above are used.
        """

        from app.models.agent_v21 import AgentPreference, AgentThreadMessage
        from app.models.prism_v22 import Prism, PrismWorkingAgreement
        from app.services.agent_preference_service import AgentPreferenceService
        from app.services.llm_service import LLMService
        from app.services.people_directory_service import PeopleDirectoryService

        prism = db.get(Prism, prism_id) if prism_id else None
        normalized = " ".join(text.split())
        fallback = ChatIntentService.reply(
            text,
            prism_name=prism.name if prism else None,
            prism_description=prism.description if prism else None,
        )
        if (
            not normalized
            or len(normalized) > 200
            or len(normalized.split()) > 20
            or _WORK_WORDS.search(normalized)
            or _names_a_person(db, normalized)
            # A question that is not about the Prism itself ("has it gone out yet?") is about work.
            or ("?" in normalized and not _ABOUT_YOU.search(normalized))
        ):
            return fallback
        try:
            agreement = (
                db.scalar(
                    select(PrismWorkingAgreement)
                    .where(PrismWorkingAgreement.prism_id == prism.id)
                    .order_by(PrismWorkingAgreement.revision.desc())
                )
                if prism
                else None
            )
            recent = list(
                db.scalars(
                    select(AgentThreadMessage)
                    # Only the casual back-and-forth: work answers and drafts are never replayed.
                    .where(
                        AgentThreadMessage.thread_id == thread_id,
                        AgentThreadMessage.job_id.is_(None),
                    )
                    .order_by(AgentThreadMessage.created_at.desc())
                    .limit(6)
                )
            )[::-1]
            preferences: list[AgentPreference] = AgentPreferenceService.active(
                db, thread_id=thread_id
            )
            name = prism.name if prism else "Prism"
            decision = LLMService.complete(
                prompt=CHAT_PROMPT.format(
                    name=name, role=(prism.description if prism else "Assistant")
                ),
                context={
                    "chat_message": normalized,
                    "about_the_manager": PeopleDirectoryService.manager_context(db),
                    "people_you_know": PeopleDirectoryService.people_context(
                        db, prism_id, limit=40
                    ),
                    "working_agreement": agreement.agreement if agreement else None,
                    "manager_instructions": [item.instruction for item in preferences],
                    "recent_conversation": [
                        {
                            "from": "manager" if m.role == "manager" else name,
                            "text": m.content[:400],
                        }
                        for m in recent
                    ],
                },
                output_model=ChatDecision,
                feature="prism_chat_reply",
            )
        except Exception:  # noqa: BLE001 - the model is optional here; work requests still flow on
            logger.info("chat_reply_model_unavailable", exc_info=False)
            return fallback
        if decision.needs_work_lookup:
            return None
        reply = decision.reply.strip()
        first_name = (PeopleDirectoryService.manager_context(db) or {}).get("first_name", "")
        greeted = _GREETS_SOMEONE.match(reply)
        if len(reply) > 600 or (greeted and greeted.group(1).lower() != first_name.lower()):
            return None  # that is a message to someone else, not a chat reply
        return reply or fallback
