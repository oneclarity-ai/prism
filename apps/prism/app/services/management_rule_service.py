from __future__ import annotations

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.enums import BlockerSeverity, BlockerStatus, CommitmentStatus, TaskStatus
from app.models.task import Task
from app.schemas.management import RuleFinding


class ManagementRuleService:
    """Read-only deterministic checks over objective management state."""

    @staticmethod
    def findings(db: Session) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        findings.extend(ManagementRuleService._tasks_without_expected_outcomes(db))
        findings.extend(ManagementRuleService._blockers_without_dependency_owner(db))
        findings.extend(ManagementRuleService._blockers_without_open_commitment(db))
        findings.extend(ManagementRuleService._missed_commitments(db))
        findings.extend(ManagementRuleService._high_severity_blockers(db))
        return findings

    @staticmethod
    def _tasks_without_expected_outcomes(db: Session) -> list[RuleFinding]:
        tasks = db.scalars(
            select(Task).where(
                Task.status.not_in([TaskStatus.DONE, TaskStatus.CANCELLED]),
                or_(
                    Task.expected_outcome.is_(None),
                    func.length(func.trim(Task.expected_outcome)) == 0,
                ),
            )
        )
        return [
            RuleFinding(
                rule_code="task_missing_expected_outcome",
                severity=BlockerSeverity.MEDIUM,
                reason="Active task has no concrete expected outcome",
                task_id=task.id,
                project_id=task.project_id,
                employee_id=task.owner_id,
            )
            for task in tasks
        ]

    @staticmethod
    def _blockers_without_dependency_owner(db: Session) -> list[RuleFinding]:
        blockers = db.scalars(
            select(Blocker).where(
                Blocker.status == BlockerStatus.OPEN,
                Blocker.dependency_owner_id.is_(None),
            )
        )
        return [
            RuleFinding(
                rule_code="blocker_missing_dependency_owner",
                severity=blocker.severity,
                reason="Open blocker has no dependency owner",
                blocker_id=blocker.id,
                task_id=blocker.task_id,
                employee_id=blocker.blocked_employee_id,
            )
            for blocker in blockers
        ]

    @staticmethod
    def _blockers_without_open_commitment(db: Session) -> list[RuleFinding]:
        open_commitment = exists(
            select(Commitment.id).where(
                Commitment.blocker_id == Blocker.id,
                Commitment.status == CommitmentStatus.OPEN,
            )
        )
        blockers = db.scalars(
            select(Blocker).where(Blocker.status == BlockerStatus.OPEN, ~open_commitment)
        )
        return [
            RuleFinding(
                rule_code="blocker_missing_open_commitment",
                severity=blocker.severity,
                reason="Open blocker has no active commitment ETA",
                blocker_id=blocker.id,
                task_id=blocker.task_id,
                employee_id=blocker.dependency_owner_id or blocker.blocked_employee_id,
            )
            for blocker in blockers
        ]

    @staticmethod
    def _missed_commitments(db: Session) -> list[RuleFinding]:
        commitments = db.scalars(
            select(Commitment).where(Commitment.status == CommitmentStatus.MISSED)
        )
        return [
            RuleFinding(
                rule_code="missed_commitment",
                severity=BlockerSeverity.HIGH,
                reason="Commitment deadline was missed and needs a reason or revised ETA",
                commitment_id=commitment.id,
                task_id=commitment.task_id,
                employee_id=commitment.employee_id,
            )
            for commitment in commitments
        ]

    @staticmethod
    def _high_severity_blockers(db: Session) -> list[RuleFinding]:
        blockers = db.scalars(
            select(Blocker).where(
                Blocker.status == BlockerStatus.OPEN,
                Blocker.severity.in_([BlockerSeverity.HIGH, BlockerSeverity.CRITICAL]),
            )
        )
        return [
            RuleFinding(
                rule_code="high_severity_blocker",
                severity=blocker.severity,
                reason="Open blocker has high management impact",
                blocker_id=blocker.id,
                task_id=blocker.task_id,
                employee_id=blocker.blocked_employee_id,
            )
            for blocker in blockers
        ]
