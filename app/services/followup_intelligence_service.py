"""Value-aware follow-up candidates. This service never sends messages itself."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.automation_action import AutomationAction
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import (
    AutomationActionStatus,
    BlockerStatus,
    CommitmentStatus,
    MessageDirection,
)
from app.models.message import Message
from app.models.response_state import ConversationQuestion
from app.services.dependency_graph_service import DependencyGraphService


class FollowUpIntelligenceService:
    DEFAULT_COOLDOWN = timedelta(hours=1)

    @staticmethod
    def candidates(
        db: Session,
        *,
        as_of: datetime | None = None,
        eligible_employee_ids: set[uuid.UUID] | None = None,
        not_before: datetime | None = None,
    ) -> list[dict]:
        """Return follow-up candidates that are safe for the current run.

        ``not_before`` is the start of an automation run when messages may be
        sent.  It prevents a newly started run from sweeping up unanswered
        questions, commitments, or blockers left by a previous session.
        """
        now = as_of or datetime.now(timezone.utc)
        candidates: list[dict] = []
        managed_ids = set(
            db.scalars(
                select(Employee.id).where(
                    Employee.is_active.is_(True), Employee.is_managed.is_(True)
                )
            )
        )
        if eligible_employee_ids is not None:
            managed_ids &= eligible_employee_ids
        for commitment in db.scalars(
            select(Commitment)
            .where(Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.MISSED]))
            .order_by(Commitment.deadline)
        ):
            if not FollowUpIntelligenceService._is_in_run_window(commitment.created_at, not_before):
                continue
            blocker = db.get(Blocker, commitment.blocker_id) if commitment.blocker_id else None
            if commitment.employee_id not in managed_ids and (
                blocker is None or blocker.blocked_employee_id not in managed_ids
            ):
                continue
            if commitment.deadline >= now:
                continue
            downstream = DependencyGraphService.affected_by(db, "employee", commitment.employee_id)
            overdue = now - commitment.deadline
            last_inbound = db.scalar(
                select(
                    func.max(func.coalesce(Message.external_created_at, Message.created_at))
                ).where(
                    Message.employee_id == commitment.employee_id,
                    Message.direction == MessageDirection.INBOUND,
                )
            )
            recent_response = last_inbound is not None and last_inbound >= commitment.deadline
            last_followup = db.scalar(
                select(func.max(AutomationAction.executed_at)).where(
                    AutomationAction.commitment_id == commitment.id,
                    AutomationAction.status == AutomationActionStatus.DELIVERED,
                )
            )
            cooled_down = (
                last_followup is None
                or last_followup <= now - FollowUpIntelligenceService.DEFAULT_COOLDOWN
            )
            useful = bool(downstream) or overdue >= timedelta(hours=2)
            if recent_response or not cooled_down or not useful:
                continue
            candidates.append(
                {
                    "kind": "overdue_commitment",
                    "id": commitment.id,
                    "target_employee_id": commitment.employee_id,
                    "related_issue_id": commitment.blocker_id,
                    "reason": "Commitment passed {} minutes ago{}.".format(
                        int(overdue.total_seconds() // 60),
                        " and downstream work remains dependent on it" if downstream else "",
                    ),
                    "evidence": [f"commitment:{commitment.id}"]
                    + [f"blocker:{commitment.blocker_id}" if commitment.blocker_id else ""],
                    "affected": downstream,
                    "confidence": 0.95 if downstream else 0.8,
                }
            )

        for blocker in db.scalars(select(Blocker).where(Blocker.status == BlockerStatus.OPEN)):
            if not FollowUpIntelligenceService._is_in_run_window(blocker.created_at, not_before):
                continue
            if blocker.blocked_employee_id not in managed_ids:
                continue
            if blocker.updated_at > now - timedelta(days=2):
                continue
            owners = blocker.dependency_owner_ids
            if not owners:
                continue
            latest_commitment = db.scalar(
                select(Commitment)
                .where(
                    Commitment.blocker_id == blocker.id,
                    Commitment.status == CommitmentStatus.OPEN,
                )
                .order_by(Commitment.deadline.desc())
                .limit(1)
            )
            if latest_commitment is not None:
                continue
            for owner in owners:
                candidates.append(
                    {
                        "kind": "silent_blocker",
                        "id": blocker.id,
                        "target_employee_id": owner,
                        "related_issue_id": blocker.id,
                        "reason": "The blocker has had no meaningful state change for at least two days and someone remains blocked.",
                        "evidence": [f"blocker:{blocker.id}"],
                        "affected": [
                            {
                                "entity_type": "employee",
                                "id": str(blocker.blocked_employee_id),
                                "depth": 1,
                            }
                        ],
                        "confidence": 0.82,
                    }
                )

        for question in db.scalars(
            select(ConversationQuestion).where(
                ConversationQuestion.answered_at.is_(None),
                ConversationQuestion.created_at <= now - timedelta(hours=4),
            )
        ):
            if not FollowUpIntelligenceService._is_in_run_window(question.created_at, not_before):
                continue
            target = question.asked_to_employee_id
            if target is None:
                continue
            if eligible_employee_ids is not None and target not in eligible_employee_ids:
                continue
            blocker = db.get(Blocker, question.blocker_id) if question.blocker_id else None
            if target not in managed_ids and (
                blocker is None or blocker.blocked_employee_id not in managed_ids
            ):
                continue
            candidates.append(
                {
                    "kind": "unanswered_question",
                    "id": question.id,
                    "target_employee_id": target,
                    "related_issue_id": question.blocker_id,
                    "reason": "A relevant question remains unanswered for at least four hours.",
                    "evidence": [f"question:{question.id}", f"message:{question.message_id}"],
                    "affected": [],
                    "confidence": 0.75,
                }
            )
        return [
            {**item, "evidence": [value for value in item["evidence"] if value]}
            for item in candidates
        ]

    @staticmethod
    def _is_in_run_window(created_at: datetime, not_before: datetime | None) -> bool:
        return not_before is None or created_at >= not_before
