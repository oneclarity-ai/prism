from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
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
from app.models.employee import Employee
from app.models.escalation import Escalation
from app.models.escalation_decision import EscalationDecision
from app.models.project import Project
from app.models.task import Task


def test_management_findings_and_yash_approval_escalations() -> None:
    suffix = uuid.uuid4().hex[:12]
    client = TestClient(app)
    employee_id: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    blocker_id: Optional[str] = None
    escalation_ids: list[str] = []

    try:
        employee = client.post(
            "/api/v1/employees",
            json={"name": "Escalation Owner", "email": "escalation-{}@example.invalid".format(suffix), "role": "Engineer"},
        )
        assert employee.status_code == 201
        employee_id = employee.json()["id"]

        project = client.post(
            "/api/v1/projects",
            json={"name": "Escalation Project", "owner_id": employee_id, "target_date": "2026-12-31"},
        )
        assert project.status_code == 201
        project_id = project.json()["id"]

        task = client.post(
            "/api/v1/tasks",
            json={
                "owner_id": employee_id,
                "project_id": project_id,
                "title": "Review architecture",
                "expected_outcome": "A documented architecture decision",
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        blocker = client.post(
            "/api/v1/blockers",
            json={
                "task_id": task_id,
                "blocked_employee_id": employee_id,
                "description": "Architecture dependency is unowned",
                "severity": "high",
            },
        )
        assert blocker.status_code == 201
        blocker_id = blocker.json()["id"]

        findings = client.get("/api/v1/management/rule-findings")
        assert findings.status_code == 200
        finding_codes = {
            finding["rule_code"]
            for finding in findings.json()
            if finding["blocker_id"] == blocker_id
        }
        assert {
            "blocker_missing_dependency_owner",
            "blocker_missing_open_commitment",
            "high_severity_blocker",
        }.issubset(finding_codes)

        target_change = client.post(
            "/api/v1/projects/{}/target-date-change-requests".format(project_id),
            json={"requested_target_date": "2027-01-15", "reason": "Vendor dependency moved"},
        )
        assert target_change.status_code == 201
        escalation_ids.append(target_change.json()["id"])
        assert target_change.json()["escalation_type"] == "project_deadline_change"
        assert target_change.json()["requires_yash_approval"] is True
        assert target_change.json()["status"] == "pending_approval"
        assert client.get("/api/v1/projects/{}".format(project_id)).json()["target_date"] == "2026-12-31"
        approved = client.post(
            "/api/v1/escalations/{}/approve".format(target_change.json()["id"]),
            json={"decided_by": employee_id, "reason": "Approved after reviewing the vendor plan"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert client.get("/api/v1/projects/{}".format(project_id)).json()["target_date"] == "2027-01-15"
        decisions = client.get("/api/v1/escalations/{}/decisions".format(target_change.json()["id"]))
        assert decisions.status_code == 200
        assert decisions.json()[0]["decision"] == "approved"
        assert client.post(
            "/api/v1/escalations/{}/approve".format(target_change.json()["id"]),
            json={"decided_by": employee_id, "reason": "Second decision must fail"},
        ).status_code == 422

        task_change = client.post(
            "/api/v1/tasks/{}/deadline-change-requests".format(task_id),
            json={
                "requested_deadline": "2027-01-20T10:00:00Z",
                "reason": "The vendor review changes the delivery sequence",
            },
        )
        assert task_change.status_code == 201
        escalation_ids.append(task_change.json()["id"])
        assert task_change.json()["status"] == "pending_approval"
        assert client.get("/api/v1/tasks/{}".format(task_id)).json()["deadline"] is None
        assert client.post(
            "/api/v1/escalations/{}/approve".format(task_change.json()["id"]),
            json={"decided_by": employee_id, "reason": "Approved revised delivery plan"},
        ).status_code == 200
        saved_deadline = client.get("/api/v1/tasks/{}".format(task_id)).json()["deadline"]
        assert datetime.fromisoformat(saved_deadline).astimezone(timezone.utc) == datetime(
            2027, 1, 20, 10, 0, tzinfo=timezone.utc
        )

        architecture_change = client.post(
            "/api/v1/escalations",
            json={
                "escalation_type": "architecture_change",
                "reason": "Proposed database topology change",
                "requires_yash_approval": False,
                "project_id": project_id,
            },
        )
        assert architecture_change.status_code == 201
        escalation_id = architecture_change.json()["id"]
        escalation_ids.append(escalation_id)
        assert architecture_change.json()["requires_yash_approval"] is True
        assert architecture_change.json()["status"] == "pending_approval"
        assert client.post("/api/v1/escalations/{}/acknowledge".format(escalation_id)).status_code == 422
        rejected = client.post(
            "/api/v1/escalations/{}/reject".format(escalation_id),
            json={"decided_by": employee_id, "reason": "No architecture decision is authorised in V1"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
        assert client.post(
            "/api/v1/escalations/{}/resolve".format(escalation_id)
        ).status_code == 422
    finally:
        with SessionLocal() as db:
            if escalation_ids:
                db.execute(
                    delete(EscalationDecision).where(
                        EscalationDecision.escalation_id.in_(escalation_ids)
                    )
                )
            if escalation_ids:
                db.execute(delete(Escalation).where(Escalation.id.in_(escalation_ids)))
            if blocker_id is not None:
                db.execute(delete(Blocker).where(Blocker.id == blocker_id))
            if task_id is not None:
                db.execute(delete(Task).where(Task.id == task_id))
            if project_id is not None:
                db.execute(delete(Project).where(Project.id == project_id))
            if employee_id is not None:
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
