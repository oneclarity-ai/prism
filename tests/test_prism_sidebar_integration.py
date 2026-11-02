from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism
from app.schemas.prism_v22 import PrismCreate
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


def test_prism_list_carries_the_latest_message_and_who_sent_it():
    created: list[uuid.UUID] = []
    with SessionLocal() as db:
        try:
            quiet = PrismLifecycleService.create(
                db, PrismCreate(name=f"Quiet {uuid.uuid4().hex[:6]}", description="No chat yet.")
            )
            busy = PrismLifecycleService.create(
                db, PrismCreate(name=f"Busy {uuid.uuid4().hex[:6]}", description="Has a chat.")
            )
            created += [quiet.id, busy.id]
            busy = _activate(db, busy)
            _, thread = PrismConversationService.canonical_thread(db, busy.id)
            earlier = datetime.now(timezone.utc) - timedelta(hours=1)
            db.add_all(
                [
                    AgentThreadMessage(
                        thread_id=thread.id, role="manager", content="first", created_at=earlier
                    ),
                    AgentThreadMessage(
                        thread_id=thread.id,
                        role="assistant",
                        content="  Done.\n  All   sent. ",
                        created_at=earlier + timedelta(minutes=1),
                    ),
                ]
            )
            db.commit()

            rows = {p.id: p for p in PrismLifecycleService.list_prisms(db)}
            assert rows[quiet.id].last_message_preview is None
            assert rows[quiet.id].last_message_role is None
            assert rows[busy.id].last_message_role == "assistant"
            assert rows[busy.id].last_message_preview == "Done. All sent."
            assert rows[busy.id].last_message_at is not None
        finally:
            db.rollback()
            for prism_id in created:
                db.execute(delete(AgentThread).where(AgentThread.prism_id == prism_id))
                db.execute(delete(Prism).where(Prism.id == prism_id))
            db.commit()


def test_prism_colour_is_saved_validated_and_changeable():
    import pydantic

    from app.schemas.prism_v22 import PrismUpdate

    created: list[uuid.UUID] = []
    with SessionLocal() as db:
        try:
            prism = PrismLifecycleService.create(
                db,
                PrismCreate(
                    name=f"Colour {uuid.uuid4().hex[:6]}", description="Has a colour.", color="teal"
                ),
            )
            created.append(prism.id)
            assert prism.color == "teal"
            updated = PrismLifecycleService.update(
                db,
                prism.id,
                PrismUpdate(expected_lifecycle_version=prism.lifecycle_version, color="pink"),
            )
            assert updated.color == "pink"
            with pytest.raises(pydantic.ValidationError):
                PrismCreate(name="x", description="y", color="beige")
        finally:
            db.rollback()
            for prism_id in created:
                db.execute(delete(Prism).where(Prism.id == prism_id))
            db.commit()
