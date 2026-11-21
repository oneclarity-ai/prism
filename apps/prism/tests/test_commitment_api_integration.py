from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.task import Task


def test_missed_commitment_creates_immutable_revision_history() -> None:
    suffix = uuid.uuid4().hex[:12]
    client = TestClient(app)
    employee_ids: list[str] = []
    task_id: Optional[str] = None
    blocker_id: Optional[str] = None
    commitment_ids: list[str] = []

    try:
        owner = client.post(
            "/api/v1/employees",
            json={
                "name": "Task Owner",
                "email": "owner-{}@example.invalid".format(suffix),
                "role": "Engineer",
            },
        )
        dependency_owner = client.post(
            "/api/v1/employees",
            json={
                "name": "Dependency Owner",
                "email": "dependency-{}@example.invalid".format(suffix),
                "role": "Engineer",
            },
        )
        assert owner.status_code == dependency_owner.status_code == 201
        owner_id = owner.json()["id"]
        dependency_owner_id = dependency_owner.json()["id"]
        employee_ids.extend([owner_id, dependency_owner_id])

        task = client.post(
            "/api/v1/tasks",
            json={
                "owner_id": owner_id,
                "title": "Use updated schema",
                "expected_outcome": "API is integrated with the updated schema",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        blocker = client.post(
            "/api/v1/blockers",
            json={
                "task_id": task_id,
                "blocked_employee_id": owner_id,
                "dependency_owner_id": dependency_owner_id,
                "description": "Updated schema has not been supplied",
            },
        )
        assert blocker.status_code == 201
        blocker_id = blocker.json()["id"]

        commitment = client.post(
            "/api/v1/commitments",
            json={
                "employee_id": dependency_owner_id,
                "task_id": task_id,
                "blocker_id": blocker_id,
                "description": "Send the updated schema",
                "deadline": "2026-12-01T09:00:00Z",
            },
        )
        assert commitment.status_code == 201
        original_id = commitment.json()["id"]
        commitment_ids.append(original_id)

        missed = client.post("/api/v1/commitments/{}/mark-missed".format(original_id), json={})
        assert missed.status_code == 200
        assert missed.json()["status"] == "missed"

        revision = client.post(
            "/api/v1/commitments/{}/revisions".format(original_id),
            json={
                "description": "Send the revised updated schema",
                "deadline": "2026-12-02T09:00:00Z",
                "missed_reason": "The upstream data contract changed",
            },
        )
        assert revision.status_code == 201
        revised_id = revision.json()["id"]
        commitment_ids.append(revised_id)
        assert revision.json()["revised_from_id"] == original_id

        history = client.get("/api/v1/commitments/{}/history".format(revised_id))
        assert history.status_code == 200
        assert [item["id"] for item in history.json()] == [original_id, revised_id]

        original = client.get("/api/v1/commitments/{}".format(original_id))
        assert original.status_code == 200
        assert original.json()["status"] == "superseded"
        assert original.json()["missed_reason"] == "The upstream data contract changed"

        assert client.post("/api/v1/commitments/{}/complete".format(revised_id)).status_code == 200
    finally:
        with SessionLocal() as db:
            if commitment_ids:
                db.execute(delete(Commitment).where(Commitment.id.in_(commitment_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if task_id is not None:
                db.execute(delete(Task).where(Task.id == task_id))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
