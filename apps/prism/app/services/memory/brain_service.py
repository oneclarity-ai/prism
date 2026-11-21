from __future__ import annotations

import logging
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.memory.brain import BrainEntry
from app.models.prisms.prism_v22 import Prism
from app.services.errors import NotFoundError

logger = logging.getLogger(__name__)

CONTEXT_LIMIT = 3500
MAX_PROPOSED = 40
MIN_LEARN_CHARS = 40

LEARN_PROMPT = """You keep the shared memory of an organisation that a manager's Prisms (AI assistants) all read.
From the manager's message, pull out at most 3 durable facts about the organisation that any Prism should
know: the company, its products, customers, people and their roles, terms, standing preferences, goals.
Skip one-off tasks, questions, greetings, and anything already in known_titles. Each fact gets a short
title and one or two plain sentences stating only what the manager said, never guessed. Return no facts
when there is nothing durable."""


class _Fact(BaseModel):
    title: str = Field(default="", max_length=120)
    body: str = Field(default="", max_length=500)


class _Learned(BaseModel):
    facts: list[_Fact] = Field(default_factory=list, max_length=3)


def _clean(text: str, limit: int) -> str:
    return " ".join(str(text).split())[:limit]


class BrainService:
    """The memory every Prism shares: org facts the user writes, facts learned from chats, Prism work notes."""

    @staticmethod
    def get(db: Session, entry_id: uuid.UUID) -> BrainEntry:
        entry = db.get(BrainEntry, entry_id)
        if entry is None:
            raise NotFoundError("Brain entry was not found")
        return entry

    @staticmethod
    def list(db: Session) -> list[dict]:
        rows = db.execute(
            select(BrainEntry, Prism.name)
            .outerjoin(Prism, Prism.id == BrainEntry.prism_id)
            .where(BrainEntry.status != "rejected")
            .order_by(BrainEntry.updated_at.desc())
        ).all()
        out = []
        for entry, prism_name in rows:
            entry.prism_name = prism_name
            out.append(entry)
        return out

    @classmethod
    def create(cls, db: Session, title: str, body: str) -> BrainEntry:
        entry = BrainEntry(
            title=_clean(title, 200), body=body.strip()[:2000], status="approved", source="user"
        )
        db.add(entry)
        db.commit()
        return entry

    @classmethod
    def update(cls, db: Session, entry_id: uuid.UUID, title: str | None, body: str | None):
        entry = cls.get(db, entry_id)
        if title is not None:
            entry.title = _clean(title, 200)
        if body is not None:
            entry.body = body.strip()[:2000]
        db.commit()
        return entry

    @classmethod
    def decide(cls, db: Session, entry_id: uuid.UUID, approve: bool) -> BrainEntry:
        entry = cls.get(db, entry_id)
        entry.status = "approved" if approve else "rejected"
        db.commit()
        return entry

    @classmethod
    def delete(cls, db: Session, entry_id: uuid.UUID) -> None:
        db.delete(cls.get(db, entry_id))
        db.commit()

    @staticmethod
    def context(db: Session) -> str:
        """The compact text every Prism is given. Only approved entries; empty when there are none."""

        rows = db.execute(
            select(BrainEntry, Prism.name)
            .outerjoin(Prism, Prism.id == BrainEntry.prism_id)
            .where(BrainEntry.status == "approved")
            .order_by(BrainEntry.created_at)
        ).all()
        facts = [f"- {e.title}: {e.body}" for e, _ in rows if e.source != "prism"]
        work = [f"- {name or e.title}: {e.body}" for e, name in rows if e.source == "prism"]
        parts = []
        if facts:
            parts.append("About the organisation:\n" + "\n".join(facts))
        if work:
            parts.append("What the other Prisms are working on:\n" + "\n".join(work))
        return "\n\n".join(parts)[:CONTEXT_LIMIT]

    @classmethod
    def note_work(cls, db: Session, prism: Prism, title: str, summary: str) -> None:
        """A Prism's own note of its latest work, replaced as it does more. Never needs approval."""

        line = _clean(f"{title}: {summary}", 300)
        entry = db.scalar(
            select(BrainEntry).where(BrainEntry.prism_id == prism.id, BrainEntry.source == "prism")
        )
        if entry is None:
            db.add(
                BrainEntry(
                    title=_clean(prism.name, 200),
                    body=line,
                    status="approved",
                    source="prism",
                    prism_id=prism.id,
                )
            )
        else:
            earlier = [part for part in entry.body.split(" | ") if part != line][:2]
            entry.body = " | ".join([line, *earlier])[:900]
        db.commit()

    @classmethod
    def learn(cls, db: Session, prism: Prism, text: str) -> int:
        """Propose durable facts from one manager message; the user approves them before Prisms see them."""

        text = _clean(text, 1500)
        if len(text) < MIN_LEARN_CHARS:
            return 0
        from app.services.llm.llm_service import LLMService

        known = list(db.scalars(select(BrainEntry.title)))
        pending = len(
            list(db.scalars(select(BrainEntry.id).where(BrainEntry.status == "proposed")))
        )
        if pending >= MAX_PROPOSED:
            return 0
        result = LLMService.complete(
            prompt=LEARN_PROMPT,
            context={"message": text, "prism": prism.name, "known_titles": known[:80]},
            output_model=_Learned,
            feature="brain_learn",
        )
        seen = {title.casefold() for title in known}
        added = 0
        for fact in result.facts:
            title, body = _clean(fact.title, 200), _clean(fact.body, 500)
            if not title or not body or title.casefold() in seen:
                continue
            seen.add(title.casefold())
            db.add(
                BrainEntry(
                    title=title, body=body, status="proposed", source="chat", prism_id=prism.id
                )
            )
            added += 1
        db.commit()
        return added

    @classmethod
    def learn_in_background(cls, prism_id: uuid.UUID, text: str) -> None:
        try:
            with SessionLocal() as db:
                prism = db.get(Prism, prism_id)
                if prism is not None:
                    cls.learn(db, prism, text)
        except Exception:  # noqa: BLE001 - learning is a bonus; chat must never depend on it
            logger.info("brain_learn_failed", exc_info=False)
