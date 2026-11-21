from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.enums import ActivityEventType, MemoryFactStatus, MemoryPredicate, VisibilityScope
from app.models.memory import ActivityEvent, MemoryFact
from app.schemas.memory import MemoryFactCreate
from app.services.memory_service import MemoryService


def test_memory_is_temporal_idempotent_and_private() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    fact_ids: list[uuid.UUID] = []
    event_id: uuid.UUID | None = None
    try:
        with SessionLocal() as db:
            avery = Employee(
                name="Avery Memory",
                email="avery-memory-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            ben = Employee(
                name="Ben Memory",
                email="ben-memory-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            db.add_all([avery, ben])
            db.flush()
            employee_ids = [avery.id, ben.id]
            observed = datetime.now(timezone.utc)
            first = MemoryService.create_fact(
                db,
                MemoryFactCreate(
                    subject_type="employee",
                    subject_id=avery.id,
                    subject_text="Avery",
                    predicate=MemoryPredicate.OWNS,
                    object_type="system",
                    object_text="Status API",
                    observed_at=observed,
                    visibility_scope=VisibilityScope.MANAGER_ONLY,
                ),
            )
            second = MemoryService.create_fact(
                db,
                MemoryFactCreate(
                    subject_type="employee",
                    subject_id=avery.id,
                    subject_text="Avery",
                    predicate=MemoryPredicate.OWNS,
                    object_type="system",
                    object_text="Connector API",
                    observed_at=observed + timedelta(minutes=1),
                    visibility_scope=VisibilityScope.MANAGER_ONLY,
                ),
            )
            private = MemoryService.create_fact(
                db,
                MemoryFactCreate(
                    subject_type="employee",
                    subject_id=ben.id,
                    subject_text="Ben",
                    predicate=MemoryPredicate.WORKING_ON,
                    object_type="note",
                    object_text="Private 1:1 matter",
                    observed_at=observed,
                    visibility_scope=VisibilityScope.PRIVATE_1TO1,
                ),
            )
            first_event = MemoryService.record_event(
                db,
                event_type=ActivityEventType.BLOCKER_CREATED,
                entity_type="test",
                entity_id=None,
                source_type="test",
                source_id=None,
                occurred_at=observed,
                subject_employee_id=avery.id,
                idempotency_key="memory-test-event-{}".format(suffix),
            )
            same_event = MemoryService.record_event(
                db,
                event_type=ActivityEventType.BLOCKER_CREATED,
                entity_type="test",
                entity_id=None,
                source_type="test",
                source_id=None,
                occurred_at=observed,
                subject_employee_id=avery.id,
                idempotency_key="memory-test-event-{}".format(suffix),
            )
            db.commit()
            fact_ids = [first.id, second.id, private.id]
            event_id = first_event.id
            assert same_event.id == first_event.id
            assert first.status == MemoryFactStatus.SUPERSEDED
            assert first.valid_until == second.observed_at
            context = MemoryService.compile_context(db, avery.id)
            assert any("Connector API" in fact for fact in context.relevant_facts)
            assert not any("Private 1:1" in fact for fact in context.relevant_facts)
    finally:
        with SessionLocal() as db:
            if fact_ids:
                db.execute(delete(MemoryFact).where(MemoryFact.id.in_(fact_ids)))
            if event_id is not None:
                db.execute(delete(ActivityEvent).where(ActivityEvent.id == event_id))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
