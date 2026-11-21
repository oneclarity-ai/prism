from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.prisms.agent_v21 import AgentFeedbackEvent, AgentPreference, AgentThread
from app.schemas.prisms.agent_v21 import (
    AgentPreferenceCreate,
    AgentPreferenceUpdate,
    PrismPreferenceUpdate,
)
from app.services.errors import NotFoundError


class AgentPreferenceService:
    @staticmethod
    def active(db: Session, *, thread_id: uuid.UUID | None = None) -> list[AgentPreference]:
        now = datetime.now(timezone.utc)
        prism_id = None
        if thread_id:
            thread = db.get(AgentThread, thread_id)
            prism_id = thread.prism_id if thread else None
        # A specialized Prism must never inherit preferences from another
        # Prism—or the old, unscoped v2.1 assistant.
        if prism_id is not None:
            return list(
                db.scalars(
                    select(AgentPreference)
                    .where(
                        AgentPreference.prism_id == prism_id,
                        AgentPreference.is_active.is_(True),
                        or_(
                            AgentPreference.expires_at.is_(None),
                            AgentPreference.expires_at > now,
                        ),
                    )
                    .order_by(AgentPreference.created_at)
                )
            )
        scope = [AgentPreference.scope == "general"]
        if thread_id:
            scope.append(
                (AgentPreference.scope == "teams_chat")
                & (AgentPreference.source_thread_id == thread_id)
            )
        return list(
            db.scalars(
                select(AgentPreference)
                .where(
                    AgentPreference.is_active.is_(True),
                    or_(AgentPreference.expires_at.is_(None), AgentPreference.expires_at > now),
                    or_(*scope),
                )
                .order_by(AgentPreference.created_at)
            )
        )

    @staticmethod
    def list(db: Session) -> list[AgentPreference]:
        # Prism preferences are managed per Prism; this is the legacy, unscoped list.
        return list(
            db.scalars(
                select(AgentPreference)
                .where(AgentPreference.prism_id.is_(None))
                .order_by(AgentPreference.created_at.desc())
            )
        )

    @staticmethod
    def create(db: Session, data: AgentPreferenceCreate) -> AgentPreference:
        if data.source_thread_id and db.get(AgentThread, data.source_thread_id) is None:
            raise NotFoundError("Agent thread was not found")
        item = AgentPreference(
            instruction=data.instruction.strip(),
            scope=data.scope,
            source_kind="explicit_manager_instruction",
            source_thread_id=data.source_thread_id,
        )
        db.add(item)
        db.flush()
        db.add(
            AgentFeedbackEvent(
                event_type="preference_created",
                details={"preference_id": str(item.id), "scope": item.scope},
            )
        )
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list_for_prism(db: Session, prism_id: uuid.UUID) -> list[AgentPreference]:
        return list(
            db.scalars(
                select(AgentPreference)
                .where(AgentPreference.prism_id == prism_id)
                .order_by(AgentPreference.created_at.desc())
            )
        )

    @staticmethod
    def remember_for_prism(
        db: Session, *, prism_id: uuid.UUID, thread_id: uuid.UUID, instruction: str
    ) -> AgentPreference:
        item = AgentPreference(
            prism_id=prism_id,
            instruction=instruction.strip(),
            scope="general",
            source_kind="explicit_manager_instruction",
            source_thread_id=thread_id,
        )
        db.add(item)
        db.flush()
        db.add(
            AgentFeedbackEvent(
                event_type="prism_preference_created",
                details={"preference_id": str(item.id), "prism_id": str(prism_id)},
            )
        )
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def _for_prism(db: Session, prism_id: uuid.UUID, preference_id: uuid.UUID) -> AgentPreference:
        item = db.get(AgentPreference, preference_id)
        if item is None or item.prism_id != prism_id:
            raise NotFoundError("Agent preference was not found")
        return item

    @staticmethod
    def update_for_prism(
        db: Session, prism_id: uuid.UUID, preference_id: uuid.UUID, data: PrismPreferenceUpdate
    ) -> AgentPreference:
        item = AgentPreferenceService._for_prism(db, prism_id, preference_id)
        if data.instruction is not None:
            item.instruction = data.instruction.strip()
        if data.is_active is not None:
            item.is_active = data.is_active
        db.add(
            AgentFeedbackEvent(
                event_type="prism_preference_updated",
                details={"preference_id": str(item.id), "prism_id": str(prism_id)},
            )
        )
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete_for_prism(db: Session, prism_id: uuid.UUID, preference_id: uuid.UUID) -> None:
        item = AgentPreferenceService._for_prism(db, prism_id, preference_id)
        db.add(
            AgentFeedbackEvent(
                event_type="prism_preference_deleted",
                details={"preference_id": str(item.id), "prism_id": str(prism_id)},
            )
        )
        db.delete(item)
        db.commit()

    @staticmethod
    def update(
        db: Session, preference_id: uuid.UUID, data: AgentPreferenceUpdate
    ) -> AgentPreference:
        item = db.get(AgentPreference, preference_id)
        if item is None:
            raise NotFoundError("Agent preference was not found")
        item.instruction = data.instruction.strip()
        item.scope = data.scope
        item.is_active = data.is_active
        db.add(
            AgentFeedbackEvent(
                event_type="preference_updated",
                details={"preference_id": str(item.id), "is_active": item.is_active},
            )
        )
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, preference_id: uuid.UUID) -> None:
        item = db.get(AgentPreference, preference_id)
        if item is None:
            raise NotFoundError("Agent preference was not found")
        db.add(
            AgentFeedbackEvent(
                event_type="preference_deleted",
                details={"preference_id": str(item.id), "scope": item.scope},
            )
        )
        db.delete(item)
        db.commit()
