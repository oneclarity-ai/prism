"""Prism-owned roles and reporting lines; engine positions are not the source of truth."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.enums import PrismLifecycleState
from app.models.prisms.prism_v22 import Prism, PrismLifecycleEvent
from app.services.errors import ConflictError, RuleViolationError

DEPARTMENTS = [
    "Leadership",
    "Engineering",
    "Research & Development",
    "Quality Assurance",
    "Sales",
    "Marketing",
    "Customer Success",
    "Operations",
    "Finance",
    "People",
]


def infer_role(name: str, description: str = "") -> tuple[str, str]:
    groups = [
        (("chief of staff",), "Chief of Staff", "Leadership"),
        (
            ("market research", "marketing", "content", "brand"),
            "Market Research Analyst",
            "Marketing",
        ),
        (("sales", "outreach", "leads"), "Sales Outreach Specialist", "Sales"),
        (("customer", "client success"), "Customer Intelligence Analyst", "Customer Success"),
        (("qa", "quality", "tester", "testing"), "QA Analyst", "Quality Assurance"),
        (
            ("deployment", "devops", "release", "engineering"),
            "Deployment & Engineering Specialist",
            "Engineering",
        ),
        (("research", "ai ml", "machine learning"), "AI Researcher", "Research & Development"),
        (("finance", "accounting", "budget"), "Finance Analyst", "Finance"),
        (("recruit", "human resources", "people ops"), "People Operations Specialist", "People"),
        (("email", "inbox"), "Inbox Assistant", "Operations"),
        (("delivery", "project"), "Delivery Coordinator", "Operations"),
        (("team manager",), "Team Manager", "Operations"),
        (("executive", "assistant"), "Executive Assistant", "Operations"),
    ]
    for value in (name.casefold(), description.casefold()):
        for terms, role, department in groups:
            if any(term in value for term in terms):
                return role, department
    return "Prism Specialist", "Operations"


def validate_reporting_line(
    prism_id: uuid.UUID, manager_id: uuid.UUID | None, parents: dict[uuid.UUID, uuid.UUID | None]
) -> None:
    seen = {prism_id}
    cursor = manager_id
    while cursor is not None:
        if cursor in seen:
            raise RuleViolationError("A Prism cannot report to itself or one of its reports")
        if cursor not in parents:
            raise RuleViolationError("Choose an existing, non-archived Prism as the manager")
        seen.add(cursor)
        cursor = parents[cursor]


class PrismOrganizationService:
    @staticmethod
    def lock(db: Session) -> None:
        # Serialize graph changes so two concurrent edits cannot create a reporting cycle.
        db.execute(text("SELECT pg_advisory_xact_lock(866114502)"))

    @classmethod
    def assign(cls, db: Session, prism: Prism, data: object, *, creating: bool = False) -> bool:
        rows = list(db.scalars(select(Prism).where(Prism.state != PrismLifecycleState.ARCHIVED)))
        chief = next((row for row in rows if row.is_chief_of_staff), None)
        inferred_role, inferred_department = infer_role(prism.name, prism.description)
        requested_role = getattr(data, "job_role", None)
        role = requested_role or (inferred_role if creating else prism.job_role)
        department = getattr(data, "department", None) or (
            inferred_department if creating else prism.department
        )
        is_chief = " ".join(role.casefold().split()) == "chief of staff"
        if not creating and prism.is_chief_of_staff and not is_chief:
            raise RuleViolationError(
                "The Chief of Staff role must remain assigned to your team lead"
            )
        if is_chief and chief is not None and chief.id != prism.id:
            raise ConflictError("Your team already has a Chief of Staff")
        fields_set = getattr(data, "model_fields_set", set())
        if creating or "reports_to_prism_id" in fields_set:
            manager_id = getattr(data, "reports_to_prism_id", None)
        else:
            manager_id = prism.reports_to_prism_id
        if is_chief:
            if manager_id is not None:
                raise RuleViolationError("The Chief of Staff reports directly to you")
            department = "Leadership"
        else:
            if chief is None and requested_role is not None:
                raise RuleViolationError("Create your Chief of Staff first")
            manager_id = manager_id or (chief.id if chief else None)
        validate_reporting_line(
            prism.id, manager_id, {row.id: row.reports_to_prism_id for row in rows}
        )
        changed = (
            prism.job_role,
            prism.department,
            prism.reports_to_prism_id,
            prism.is_chief_of_staff,
        ) != (role, department, manager_id, is_chief)
        prism.job_role, prism.department = role, department
        prism.reports_to_prism_id, prism.is_chief_of_staff = manager_id, is_chief
        if changed and not creating:
            cls.audit(
                db,
                prism,
                "organization_updated",
                "Role, department, or reporting line updated by the manager",
            )
        return changed

    @staticmethod
    def audit(db: Session, prism: Prism, event_type: str, reason: str) -> None:
        sequence = (
            int(
                db.scalar(
                    select(func.max(PrismLifecycleEvent.sequence)).where(
                        PrismLifecycleEvent.prism_id == prism.id
                    )
                )
                or 0
            )
            + 1
        )
        db.add(
            PrismLifecycleEvent(
                prism_id=prism.id,
                sequence=sequence,
                event_type=event_type,
                previous_state=prism.state,
                target_state=prism.state,
                reason=reason,
            )
        )

    @classmethod
    def before_archive(cls, db: Session, prism: Prism) -> None:
        rows = list(db.scalars(select(Prism).where(Prism.state != PrismLifecycleState.ARCHIVED)))
        if prism.is_chief_of_staff and any(row.id != prism.id for row in rows):
            raise RuleViolationError(
                "The Chief of Staff cannot be archived while other Prisms remain on the team"
            )
        chief = next((row for row in rows if row.is_chief_of_staff and row.id != prism.id), None)
        for child in rows:
            if child.reports_to_prism_id == prism.id:
                child.reports_to_prism_id = chief.id if chief else None
                child.lifecycle_version += 1
                cls.audit(
                    db,
                    child,
                    "reporting_line_changed",
                    "Reporting line reassigned after its manager was archived",
                )
