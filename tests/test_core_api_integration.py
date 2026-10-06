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
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task


def test_employee_project_task_workflow() -> None:
    suffix = uuid.uuid4().hex[:12]
    manager_email = "manager-{}@example.invalid".format(suffix)
    employee_email = "employee-{}@example.invalid".format(suffix)
    client = TestClient(app)
    employee_ids: list[str] = []
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    blocker_id: Optional[str] = None
    daily_update_id: Optional[str] = None

    try:
        manager_response = client.post(
            "/api/v1/employees",
            json={"name": "Integration Manager", "email": manager_email, "role": "Manager"},
        )
        assert manager_response.status_code == 201
        manager_id = manager_response.json()["id"]
        employee_ids.append(manager_id)

        employee_response = client.post(
            "/api/v1/employees",
            json={
                "name": "Integration Employee",
                "email": employee_email,
                "role": "Engineer",
                "manager_id": manager_id,
            },
        )
        assert employee_response.status_code == 201
        employee_id = employee_response.json()["id"]
        employee_ids.append(employee_id)
        assert employee_response.json()["aliases"] == []

        alias_response = client.post(
            "/api/v1/employees/{}/aliases".format(employee_id),
            json={"alias": "Teammate-{}".format(suffix)},
        )
        assert alias_response.status_code == 201
        assert client.get("/api/v1/employees/{}".format(employee_id)).json()["aliases"] == [
            "Teammate-{}".format(suffix)
        ]
        assert (
            client.delete(
                "/api/v1/employees/{}/aliases/{}".format(employee_id, alias_response.json()["id"])
            ).status_code
            == 204
        )
        assert client.get("/api/v1/employees/{}/aliases".format(employee_id)).json() == []

        project_response = client.post(
            "/api/v1/projects",
            json={
                "name": "Integration Project",
                "owner_id": employee_id,
                "target_date": "2026-12-31",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        task_response = client.post(
            "/api/v1/tasks",
            json={
                "title": "Deliver integration example",
                "expected_outcome": "A tested workflow",
                "owner_id": employee_id,
                "project_id": project_id,
                "deadline": "2026-12-01T09:00:00Z",
            },
        )
        assert task_response.status_code == 201
        task_id = task_response.json()["id"]

        daily_update_response = client.post(
            "/api/v1/daily-updates",
            json={
                "employee_id": employee_id,
                "update_date": "2026-12-01",
                "completed_summary": "Created the project task",
                "today_summary": "Deliver the integration example",
                "expected_outcome": "A tested workflow running in staging",
            },
        )
        assert daily_update_response.status_code == 201
        daily_update_id = daily_update_response.json()["id"]
        assert (
            daily_update_response.json()["expected_outcome"]
            == "A tested workflow running in staging"
        )
        assert (
            client.get("/api/v1/daily-updates/{}".format(daily_update_id)).json()[
                "expected_outcome"
            ]
            == "A tested workflow running in staging"
        )
        assert (
            client.post(
                "/api/v1/daily-updates",
                json={
                    "employee_id": employee_id,
                    "update_date": "2026-12-01",
                    "today_summary": "Duplicate",
                },
            ).status_code
            == 409
        )

        blocker_response = client.post(
            "/api/v1/blockers",
            json={
                "task_id": task_id,
                "blocked_employee_id": employee_id,
                "dependency_owner_id": manager_id,
                "description": "Waiting for the dependency schema",
                "severity": "high",
            },
        )
        assert blocker_response.status_code == 201
        blocker_id = blocker_response.json()["id"]
        assert client.get("/api/v1/tasks/{}".format(task_id)).json()["status"] == "blocked"
        assert (
            client.patch(
                "/api/v1/tasks/{}".format(task_id), json={"status": "in_progress"}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/v1/blockers/{}".format(blocker_id), json={"status": "resolved"}
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/v1/tasks/{}".format(task_id), json={"status": "in_progress"}
            ).status_code
            == 200
        )

        assert (
            client.patch(
                "/api/v1/tasks/{}".format(task_id),
                json={"deadline": "2026-12-02T09:00:00Z"},
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/v1/projects/{}".format(project_id),
                json={"target_date": "2027-01-15"},
            ).status_code
            == 422
        )

        tasks_response = client.get("/api/v1/tasks", params={"owner_id": employee_id})
        assert tasks_response.status_code == 200
        assert tasks_response.json()["total"] == 1
        assert tasks_response.json()["items"][0]["id"] == task_id
    finally:
        with SessionLocal() as db:
            if daily_update_id is not None:
                db.execute(delete(DailyUpdate).where(DailyUpdate.id == daily_update_id))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if task_id is not None:
                db.execute(delete(Task).where(Task.id == task_id))
            if project_id is not None:
                db.execute(delete(Project).where(Project.id == project_id))
            if employee_ids:
                db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
