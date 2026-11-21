"""Server-owned conversation lookup for private v2.2 Prisms."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PrismLifecycleState
from app.models.prisms.agent_v21 import AgentThread
from app.models.prisms.prism_v22 import Prism
from app.services.errors import RuleViolationError
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService


class PrismConversationService:
    """Binds a request to its Prism before any thread or job is accessed."""

    @staticmethod
    def canonical_thread(db: Session, prism_id: uuid.UUID) -> tuple[Prism, AgentThread]:
        prism = PrismLifecycleService.get(db, prism_id)
        if prism.state != PrismLifecycleState.ACTIVE:
            raise RuleViolationError("Activate this Prism before starting its private conversation")
        thread = db.scalar(
            select(AgentThread).where(
                AgentThread.prism_id == prism.id, AgentThread.is_canonical.is_(True)
            )
        )
        if thread is None:
            thread = AgentThread(
                prism_id=prism.id,
                title=f"{prism.name} conversation",
                is_canonical=True,
                source_metadata={
                    "prism_context": {
                        "prism_id": str(prism.id),
                        "agreement_revision": prism.agreement_revision,
                    }
                },
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
        return prism, thread

    @staticmethod
    def assert_thread_belongs_to_prism(
        db: Session, *, prism_id: uuid.UUID, thread_id: uuid.UUID
    ) -> AgentThread:
        _, thread = PrismConversationService.canonical_thread(db, prism_id)
        if thread.id != thread_id:
            raise RuleViolationError("That conversation does not belong to this Prism")
        return thread
