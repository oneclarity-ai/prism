import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.prism_v22 import PrismCreate, PrismUpdate
from app.services.errors import ConflictError, RuleViolationError
from app.services.prism_organization_service import (
    PrismOrganizationService,
    infer_role,
    validate_reporting_line,
)


@pytest.mark.parametrize(
    "name,department",
    [
        ("Chief of Staff", "Leadership"),
        ("Sales Outreach", "Sales"),
        ("Market Research", "Marketing"),
        ("Customer Intelligence", "Customer Success"),
        ("QA Analyst", "Quality Assurance"),
        ("AI ML Researcher", "Research & Development"),
        ("ai researcher", "Research & Development"),
        ("Deployment Watcher", "Engineering"),
        ("Delivery Radar", "Operations"),
        ("Team Manager", "Operations"),
        ("Email Assistant", "Operations"),
    ],
)
def test_existing_prism_department_inference(name, department):
    assert infer_role(name)[1] == department


def test_reporting_validation_rejects_self_cycles_and_missing_managers():
    chief, lead, worker, missing = [uuid.uuid4() for _ in range(4)]
    parents = {chief: None, lead: chief, worker: lead}
    validate_reporting_line(worker, chief, parents)
    for subject, manager in [(lead, lead), (chief, worker), (worker, missing)]:
        with pytest.raises(RuleViolationError):
            validate_reporting_line(subject, manager, parents)


def test_explicit_reporting_reset_is_an_update_and_invalid_roles_are_rejected():
    assert PrismUpdate(expected_lifecycle_version=1, reports_to_prism_id=None)
    with pytest.raises(ValidationError):
        PrismUpdate(expected_lifecycle_version=1)
    with pytest.raises(ValidationError):
        PrismCreate(name="Sales", description="Research leads", job_role=" ")


def test_team_assignment_defaults_to_chief_and_preserves_explicit_department():
    chief_id, worker_id = uuid.uuid4(), uuid.uuid4()
    chief = SimpleNamespace(id=chief_id, is_chief_of_staff=True, reports_to_prism_id=None)
    db = SimpleNamespace(scalars=lambda _: [chief])
    prism = SimpleNamespace(
        id=worker_id,
        name="Sales Prism",
        description="Find leads",
        job_role=None,
        department=None,
        reports_to_prism_id=None,
        is_chief_of_staff=False,
    )
    payload = PrismCreate(
        name="Sales Prism",
        description="Find leads",
        job_role="Account Researcher",
        department="Enterprise Sales",
    )
    PrismOrganizationService.assign(db, prism, payload, creating=True)
    assert prism.reports_to_prism_id == chief_id
    assert prism.job_role == "Account Researcher"
    assert prism.department == "Enterprise Sales"
    with pytest.raises(ConflictError):
        PrismOrganizationService.assign(
            db,
            prism,
            PrismCreate(name="Duplicate chief", description="Lead", job_role="Chief of Staff"),
            creating=True,
        )
