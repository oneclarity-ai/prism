from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.blocker import BlockerCreate
from app.schemas.commitment import CommitmentCreate, CommitmentRevisionCreate
from app.schemas.conversation import MessageIntentCreate
from app.schemas.daily_update import DailyUpdateCreate
from app.schemas.employee import EmployeeCreate
from app.schemas.escalation import EscalationCreate
from app.schemas.management_context import ManagementContextCreate
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate


def test_employee_email_is_normalized() -> None:
    employee = EmployeeCreate(name="Avery", email="  AVERY@EXAMPLE.COM ", role="Engineer")

    assert employee.email == "avery@example.com"


def test_employee_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(name="Avery", email="not-an-email", role="Engineer")


def test_project_rejects_target_before_start_date() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="MVP", start_date="2026-10-10", target_date="2026-10-09")


def test_task_requires_outcome_and_timezone_aware_deadline() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(
            owner_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6", title="Task", expected_outcome=""
        )
    with pytest.raises(ValidationError):
        TaskCreate(
            owner_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6",
            title="Task",
            expected_outcome="A concrete delivery",
            deadline=datetime(2026, 10, 10, 9, 0),
        )


def test_daily_update_requires_todays_concrete_plan() -> None:
    with pytest.raises(ValidationError):
        DailyUpdateCreate(
            employee_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6", update_date="2026-10-10"
        )


def test_blocker_requires_description() -> None:
    with pytest.raises(ValidationError):
        BlockerCreate(blocked_employee_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6", description="")


def test_commitment_requires_timezone_and_revision_reason() -> None:
    with pytest.raises(ValidationError):
        CommitmentCreate(
            employee_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6",
            description="Provide the schema",
            deadline=datetime(2026, 10, 10, 9, 0),
        )
    with pytest.raises(ValidationError):
        CommitmentRevisionCreate(
            description="Provide the schema",
            deadline="2026-10-11T09:00:00Z",
            missed_reason="",
        )


def test_escalation_requires_specific_reason() -> None:
    with pytest.raises(ValidationError):
        EscalationCreate(escalation_type="architecture_change", reason="")


def test_message_intent_requires_content() -> None:
    with pytest.raises(ValidationError):
        MessageIntentCreate(employee_id="845e7fa0-fba6-4bf4-a0e3-cd59073bd8e6", content="")


def test_management_context_requires_meaningful_title_and_content() -> None:
    with pytest.raises(ValidationError):
        ManagementContextCreate(category="team", title="", content="Useful context")
    with pytest.raises(ValidationError):
        ManagementContextCreate(category="team", title="Team rule", content="")
