from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.management_context import ManagementContext
from app.schemas.management_context import ManagementContextCreate, ManagementContextUpdate
from app.services.errors import NotFoundError


class ManagementContextService:
    _STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "them",
        "this",
        "to",
        "we",
        "will",
        "with",
        "work",
        "working",
        "update",
        "today",
        "current",
        "currently",
    }

    @staticmethod
    def create(db: Session, data: ManagementContextCreate) -> ManagementContext:
        entry = ManagementContext(**data.model_dump())
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @staticmethod
    def list(db: Session, *, limit: int, offset: int) -> tuple[list[ManagementContext], int]:
        statement = select(ManagementContext).order_by(ManagementContext.updated_at.desc())
        count = db.scalar(select(func.count()).select_from(ManagementContext)) or 0
        return list(db.scalars(statement.limit(limit).offset(offset))), count

    @staticmethod
    def get(db: Session, entry_id: uuid.UUID) -> ManagementContext:
        entry = db.get(ManagementContext, entry_id)
        if entry is None:
            raise NotFoundError("Saved knowledge was not found")
        return entry

    @staticmethod
    def update(
        db: Session, entry_id: uuid.UUID, data: ManagementContextUpdate
    ) -> ManagementContext:
        entry = ManagementContextService.get(db, entry_id)
        for field, value in data.model_dump().items():
            setattr(entry, field, value)
        db.commit()
        db.refresh(entry)
        return entry

    @staticmethod
    def delete(db: Session, entry_id: uuid.UUID) -> None:
        entry = ManagementContextService.get(db, entry_id)
        db.delete(entry)
        db.commit()

    @staticmethod
    def _terms(value: str) -> set[str]:
        terms = set()
        for raw in re.findall(r"[a-z0-9]+", value.casefold()):
            if raw in ManagementContextService._STOP_WORDS or len(raw) < 3:
                continue
            # Lightweight stemming is sufficient for policy titles such as
            # "blocker workflow" matching an employee saying "blocked".
            term = re.sub(r"(?:ing|ers?|ed|s)$", "", raw)
            terms.add(term or raw)
        return terms

    @staticmethod
    def agent_prompt_context(
        db: Session, employee_name: str, *, query: str | None = None
    ) -> Optional[str]:
        """Return a small, active, relevant slice of manager-provided context.

        This is deliberately not a general-purpose memory search. Team-wide
        operating guidance is always eligible; people-specific notes are used
        only when the employee involved is named in the note.
        """

        first_name = employee_name.split()[0].strip()
        general_categories = ("team", "work", "communication", "escalation", "other")
        statement = (
            select(ManagementContext)
            .where(
                ManagementContext.is_active.is_(True),
                or_(
                    ManagementContext.category.in_(general_categories),
                    ManagementContext.title.ilike("%{}%".format(first_name)),
                    ManagementContext.content.ilike("%{}%".format(first_name)),
                ),
            )
            .order_by(ManagementContext.updated_at.desc())
            .limit(get_settings().management_context_max_entries)
        )
        entries = list(db.scalars(statement))
        if query is not None:
            query_terms = ManagementContextService._terms(query)
            employee_terms = ManagementContextService._terms(employee_name)
            ranked: list[tuple[int, ManagementContext]] = []
            for entry in entries:
                # Deployment lists are imported operational data, not prose
                # policy. Supplying the whole list to each reply revives old
                # assignments and contaminates unrelated messages.
                if entry.title.casefold().startswith("deployment list"):
                    continue
                title_terms = ManagementContextService._terms(entry.title)
                content_terms = ManagementContextService._terms(entry.content)
                overlap = query_terms & (title_terms | content_terms)
                employee_match = bool(employee_terms & (title_terms | content_terms))
                if not overlap and not employee_match:
                    continue
                score = len(overlap) * 10 + len(query_terms & title_terms) * 5
                score += 4 if employee_match else 0
                ranked.append((score, entry))
            ranked.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
            entries = [
                entry
                for _score, entry in ranked[
                    : get_settings().management_response_context_max_entries
                ]
            ]
        if not entries:
            return None
        return "Manager-provided context (active and bounded):\n" + "\n".join(
            "- [{}] {}: {}".format(entry.category, entry.title, entry.content[:1600])
            for entry in entries
        )
