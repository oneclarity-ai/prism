from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app
from app.models.blocker import Blocker
from app.models.employee import Employee
from app.models.enums import ActivityEventType, BlockerSeverity, MemoryFactStatus
from app.models.memory import (
    ActivityEvent,
    MemoryEpisode,
    MemoryEvidenceLink,
    MemoryFact,
    MemoryJob,
    MemoryRelation,
    MemorySource,
)
from app.services.memory_consolidation_service import MemoryConsolidationService
from app.services.memory_service import MemoryService


def test_blocker_event_becomes_provenance_linked_memory_once() -> None:
    suffix = uuid.uuid4().hex[:12]
    employee_ids: list[uuid.UUID] = []
    blocker_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    source_ids: list[uuid.UUID] = []
    fact_ids: list[uuid.UUID] = []
    relation_ids: list[uuid.UUID] = []
    episode_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            worker = Employee(
                name="Worker Memory",
                email="worker-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            owner = Employee(
                name="Owner Memory",
                email="owner-{}@example.invalid".format(suffix),
                role="Engineer",
            )
            db.add_all([worker, owner])
            db.flush()
            employee_ids = [worker.id, owner.id]
            blocker = Blocker(
                blocked_employee_id=worker.id,
                dependency_owner_id=owner.id,
                description="Test dependency {}".format(suffix),
                severity=BlockerSeverity.HIGH,
            )
            db.add(blocker)
            db.flush()
            blocker_id = blocker.id
            event = MemoryService.record_event(
                db,
                event_type=ActivityEventType.BLOCKER_CREATED,
                entity_type="blocker",
                entity_id=blocker.id,
                source_type="blocker",
                source_id=blocker.id,
                occurred_at=datetime.now(timezone.utc),
                subject_employee_id=worker.id,
                idempotency_key="memory-consolidation-{}".format(suffix),
            )
            db.commit()
            event_id = event.id

            first = MemoryConsolidationService._process_one(db, event.id)
            second = MemoryConsolidationService._process_one(db, event.id)
            assert first == {"processed": 1, "failed": 0, "facts": 1, "episodes": 1, "relations": 1}
            assert second == {
                "processed": 0,
                "failed": 0,
                "facts": 0,
                "episodes": 0,
                "relations": 0,
            }

            source_ids = list(
                db.scalars(
                    select(MemorySource.id).where(
                        MemorySource.source_type == "blocker", MemorySource.source_id == blocker.id
                    )
                )
            )
            memory_links = list(
                db.scalars(
                    select(MemoryEvidenceLink).where(
                        MemoryEvidenceLink.memory_source_id.in_(source_ids)
                    )
                )
            )
            fact_ids = [link.memory_id for link in memory_links if link.memory_kind == "fact"]
            relation_ids = [
                link.memory_id for link in memory_links if link.memory_kind == "relation"
            ]
            episode_ids = [link.memory_id for link in memory_links if link.memory_kind == "episode"]
            assert db.get(ActivityEvent, event.id).processing_status.value == "completed"
            assert db.get(MemoryFact, fact_ids[0]).status == MemoryFactStatus.CURRENT

            client = TestClient(app)
            timeline = client.get("/api/v1/memory/timeline/blocker/{}".format(blocker.id))
            assert timeline.status_code == 200
            assert timeline.json()[0]["event_type"] == "blocker_created"
            search = client.get("/api/v1/memory/search", params={"q": "Test dependency"})
            assert search.status_code == 200
            assert any(item["id"] == str(fact_ids[0]) for item in search.json()["facts"])
            evidence = client.get("/api/v1/memory/evidence/fact/{}".format(fact_ids[0]))
            assert evidence.status_code == 200
            assert evidence.json()[0]["source_type"] == "blocker"
    finally:
        with SessionLocal() as db:
            if source_ids:
                db.execute(
                    delete(MemoryEvidenceLink).where(
                        MemoryEvidenceLink.memory_source_id.in_(source_ids)
                    )
                )
            if relation_ids:
                db.execute(delete(MemoryRelation).where(MemoryRelation.id.in_(relation_ids)))
            if episode_ids:
                db.execute(delete(MemoryEpisode).where(MemoryEpisode.id.in_(episode_ids)))
            if fact_ids:
                db.execute(delete(MemoryFact).where(MemoryFact.id.in_(fact_ids)))
            if source_ids:
                db.execute(delete(MemorySource).where(MemorySource.id.in_(source_ids)))
            if event_id is not None:
                db.execute(delete(MemoryJob).where(MemoryJob.source_id == event_id))
                db.execute(delete(ActivityEvent).where(ActivityEvent.id == event_id))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
