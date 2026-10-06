from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import BlockerSeverity, CommitmentStatus, MemoryPredicate
from app.models.intelligence import (
    DependencyEdge,
    ManagementDecision,
    ManagementRisk,
    ManagerFeedback,
)
from app.models.memory import MemoryFact
from app.schemas.blocker import BlockerCreate
from app.schemas.commitment import CommitmentCreate, CommitmentRevisionCreate
from app.schemas.intelligence import DependencyEdgeCreate, ManagerFeedbackCreate
from app.schemas.memory import MemoryFactCreate
from app.services.blocker_service import BlockerService
from app.services.commitment_service import CommitmentService
from app.services.dependency_graph_service import DependencyGraphService
from app.services.management_state_service import ManagementStateService
from app.services.manager_feedback_service import ManagerFeedbackService
from app.services.memory_service import MemoryService
from app.services.temporal_memory_service import TemporalMemoryService


def test_v2_current_state_graph_and_temporal_history_work_together():
    suffix = uuid.uuid4().hex[:10]
    employee_ids = []
    try:
        with SessionLocal() as db:
            blocked = Employee(
                name="Avery " + suffix,
                email=f"avery-v2-{suffix}@example.invalid",
                role="Engineer",
                is_managed=True,
            )
            owner = Employee(
                name="Morgan " + suffix,
                email=f"morgan-v2-{suffix}@example.invalid",
                role="Engineer",
                is_managed=True,
            )
            downstream = Employee(
                name="Casey " + suffix,
                email=f"casey-v2-{suffix}@example.invalid",
                role="Engineer",
                is_managed=True,
            )
            db.add_all([blocked, owner, downstream])
            db.commit()
            employee_ids = [blocked.id, owner.id, downstream.id]
            blocker = BlockerService.create(
                db,
                BlockerCreate(
                    blocked_employee_id=blocked.id,
                    dependency_owner_id=owner.id,
                    description="Waiting for API",
                    severity=BlockerSeverity.HIGH,
                ),
            )
            commitment = CommitmentService.create(
                db,
                CommitmentCreate(
                    employee_id=owner.id,
                    blocker_id=blocker.id,
                    description="Deliver API",
                    deadline=datetime.now(timezone.utc) - timedelta(hours=3),
                    confidence=0.96,
                ),
            )
            CommitmentService.mark_missed(db, commitment.id, "ETA passed")
            revised = CommitmentService.revise(
                db,
                commitment.id,
                CommitmentRevisionCreate(
                    description="Deliver API",
                    deadline=datetime.now(timezone.utc) + timedelta(hours=2),
                    missed_reason="Additional validation",
                    confidence=0.95,
                ),
            )
            explicit = DependencyGraphService.create(
                db,
                DependencyEdgeCreate(
                    source_entity_type="employee",
                    source_entity_id=downstream.id,
                    target_entity_type="employee",
                    target_entity_id=blocked.id,
                    confidence=1.0,
                ),
            )

            state = ManagementStateService.employee_state(db, owner.id)
            graph = DependencyGraphService.graph(db)
            impact = DependencyGraphService.affected_by(db, "employee", owner.id)
            assert any(item.commitment_id == revised.id for item in state.open_commitments)
            assert any(item.id == blocker.id for item in state.others_depending_on_employee)
            assert any(edge.id == explicit.id for edge in graph.edges)
            assert {item["id"] for item in impact} >= {str(blocked.id), str(downstream.id)}
            history = CommitmentService.history(db, revised.id)
            assert [item.id for item in history] == [commitment.id, revised.id]
            assert history[0].status == CommitmentStatus.SUPERSEDED
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ManagementDecision).where(
                    ManagementDecision.related_issue_id.in_(employee_ids)
                )
            )
            db.execute(
                delete(ManagementRisk).where(ManagementRisk.source_entity_id.in_(employee_ids))
            )
            db.execute(
                delete(DependencyEdge).where(
                    (DependencyEdge.source_entity_id.in_(employee_ids))
                    | (DependencyEdge.target_entity_id.in_(employee_ids))
                )
            )
            blocker_ids = list(
                db.scalars(select(Blocker.id).where(Blocker.blocked_employee_id.in_(employee_ids)))
            )
            if blocker_ids:
                db.execute(delete(Commitment).where(Commitment.blocker_id.in_(blocker_ids)))
                db.execute(delete(Blocker).where(Blocker.id.in_(blocker_ids)))
            db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()


def test_temporal_retrieval_prefers_current_fact_over_superseded_fact():
    suffix = uuid.uuid4().hex[:10]
    employee_id = None
    try:
        with SessionLocal() as db:
            employee = Employee(
                name="Temporal " + suffix,
                email=f"temporal-{suffix}@example.invalid",
                role="Engineer",
            )
            db.add(employee)
            db.flush()
            employee_id = employee.id
            old = MemoryService.create_fact(
                db,
                MemoryFactCreate(
                    subject_type="employee",
                    subject_id=employee.id,
                    subject_text=employee.name,
                    predicate=MemoryPredicate.WORKING_ON,
                    object_type="work",
                    object_text="Old API",
                    observed_at=datetime.now(timezone.utc) - timedelta(days=1),
                    confidence=95,
                ),
            )
            current = MemoryService.create_fact(
                db,
                MemoryFactCreate(
                    subject_type="employee",
                    subject_id=employee.id,
                    subject_text=employee.name,
                    predicate=MemoryPredicate.WORKING_ON,
                    object_type="work",
                    object_text="Current API",
                    observed_at=datetime.now(timezone.utc),
                    confidence=90,
                ),
            )
            db.commit()
            result = TemporalMemoryService.retrieve(db, employee_id=employee.id)
            assert result["facts"][0]["id"] == str(current.id)
            assert all(item["id"] != str(old.id) for item in result["facts"])
            history = TemporalMemoryService.retrieve(
                db, employee_id=employee.id, include_history=True
            )
            assert {item["id"] for item in history["facts"]} >= {str(old.id), str(current.id)}
    finally:
        with SessionLocal() as db:
            if employee_id:
                db.execute(delete(MemoryFact).where(MemoryFact.subject_id == employee_id))
                db.execute(delete(Employee).where(Employee.id == employee_id))
                db.commit()


def test_manager_feedback_suppresses_followup_decision():
    suffix = uuid.uuid4().hex[:10]
    employee_id = None
    try:
        with SessionLocal() as db:
            employee = Employee(
                name="Quiet " + suffix,
                email=f"quiet-{suffix}@example.invalid",
                role="Engineer",
                is_managed=True,
            )
            db.add(employee)
            db.commit()
            employee_id = employee.id
            ManagerFeedbackService.create(
                db,
                ManagerFeedbackCreate(
                    instruction_type="person_preference",
                    scope="person",
                    employee_id=employee.id,
                    instruction="Do not follow up with this person automatically.",
                ),
            )
            # The policy is verified by the 30 scenario suite; this verifies scoped persistence/retrieval.
            applicable = ManagerFeedbackService.applicable(db, employee_id=employee.id)
            assert len(applicable) == 1
            assert "Do not follow up" in applicable[0].instruction
    finally:
        with SessionLocal() as db:
            if employee_id:
                db.execute(
                    delete(ManagerFeedback).where(ManagerFeedback.employee_id == employee_id)
                )
                db.execute(delete(Employee).where(Employee.id == employee_id))
                db.commit()
