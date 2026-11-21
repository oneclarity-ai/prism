from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.agent_v21 import AgentPreference, AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism
from app.schemas.prism_v22 import PrismCreate
from app.services.agent_preference_service import AgentPreferenceService
from app.services.prism_conversation_service import PrismConversationService
from app.services.prism_lifecycle_service import PrismLifecycleService


def _activate(db, prism: Prism) -> Prism:
    for target, event, confirmed in (
        (PrismLifecycleState.ONBOARDING, "onboarding_started", False),
        (PrismLifecycleState.AWAITING_CONFIRMATION, "agreement_prepared", False),
        (PrismLifecycleState.ACTIVE, "agreement_confirmed", True),
    ):
        prism = PrismLifecycleService.transition(
            db,
            prism.id,
            target=target,
            expected_lifecycle_version=prism.lifecycle_version,
            event_type=event,
            agreement_confirmed=confirmed,
        )
    return prism


def test_active_prisms_keep_conversations_and_memory_private() -> None:
    marker = uuid.uuid4().hex[:8]
    prism_ids: list[uuid.UUID] = []
    thread_ids: list[uuid.UUID] = []
    preference_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            first = _activate(
                db,
                PrismLifecycleService.create(
                    db,
                    PrismCreate(name=f"Executive {marker}", description="Executive updates."),
                ),
            )
            second = _activate(
                db,
                PrismLifecycleService.create(
                    db,
                    PrismCreate(name=f"QA {marker}", description="QA updates."),
                ),
            )
            prism_ids.extend([first.id, second.id])
            _, first_thread = PrismConversationService.canonical_thread(db, first.id)
            _, second_thread = PrismConversationService.canonical_thread(db, second.id)
            thread_ids.extend([first_thread.id, second_thread.id])
            assert first_thread.id != second_thread.id
            assert first_thread.prism_id == first.id
            assert second_thread.prism_id == second.id

            db.add(
                AgentThreadMessage(thread_id=first_thread.id, role="manager", content="Only first")
            )
            db.commit()
            first_memory = AgentPreferenceService.remember_for_prism(
                db,
                prism_id=first.id,
                thread_id=first_thread.id,
                instruction="Keep the executive brief concise.",
            )
            preference_ids.append(first_memory.id)

            assert [
                item.instruction
                for item in AgentPreferenceService.active(db, thread_id=first_thread.id)
            ] == ["Keep the executive brief concise."]
            assert AgentPreferenceService.active(db, thread_id=second_thread.id) == []
            assert AgentPreferenceService.list_for_prism(db, second.id) == []
            assert db.query(AgentThreadMessage).filter_by(thread_id=second_thread.id).count() == 0

    finally:
        with SessionLocal() as db:
            if preference_ids:
                db.execute(delete(AgentPreference).where(AgentPreference.id.in_(preference_ids)))
            if thread_ids:
                db.execute(delete(AgentThread).where(AgentThread.id.in_(thread_ids)))
            if prism_ids:
                db.execute(delete(Prism).where(Prism.id.in_(prism_ids)))
            db.commit()
