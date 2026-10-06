"""Execute only validated, allow-listed V2 communication decisions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.management_agent import ManagementAgent
from app.models.blocker import Blocker
from app.models.employee import Employee
from app.models.enums import AutomationActionType
from app.models.intelligence import ManagementDecision
from app.models.response_state import ConversationQuestion
from app.services.errors import DomainError
from app.services.microsoft_service import MicrosoftService


class ProactiveActionService:
    @staticmethod
    def execute_validated(db: Session, *, limit: int = 20) -> int:
        run = MicrosoftService.active_run(db)
        if run is None:
            return 0
        active_target_ids = set(run.target_employee_ids or [])
        delivered = 0
        decisions = list(db.scalars(select(ManagementDecision).where(
            ManagementDecision.status == "validated",
            ManagementDecision.action == "FOLLOW_UP",
            ManagementDecision.trigger_type.in_(["silent_blocker", "unanswered_question"]),
            ManagementDecision.decided_at >= run.started_at,
        ).order_by(ManagementDecision.decided_at).limit(limit)))
        for decision in decisions:
            employee = db.get(Employee, uuid.UUID(decision.target_employee_ids[0])) if decision.target_employee_ids else None
            blocker = db.get(Blocker, decision.related_issue_id) if decision.related_issue_id else None
            if employee is None:
                decision.status = "failed"
                decision.outcome = {"error": "Target employee no longer exists"}
                db.commit()
                continue
            if str(employee.id) not in active_target_ids:
                # A decision may have been created while a different run was
                # active. Never carry it into this manager-selected scope.
                decision.status = "skipped"
                decision.executed_at = datetime.now(timezone.utc)
                decision.outcome = {"reason": "Target is outside the active automation run"}
                db.commit()
                continue
            if decision.trigger_type == "silent_blocker" and blocker:
                text = "Could you share a quick status or ETA for {}? {} is still waiting on it.".format(
                    blocker.description.rstrip("."), blocker.blocked_employee.name.split()[0]
                )
                action_type = AutomationActionType.BLOCKER_OWNER_REQUEST
            else:
                question = db.get(ConversationQuestion, decision.trigger_id)
                text = ProactiveActionService._question_followup_text(question)
                action_type = AutomationActionType.BLOCKER_OWNER_CLARIFICATION
            try:
                sent = ManagementAgent._send_blocker_message_once(
                    db, action_type=action_type,
                    idempotency_key=f"v2-decision:{decision.id}",
                    employee=employee, blocker=blocker,
                    content=MicrosoftService.follow_up_message_for(employee.name, text),
                )
                decision.status = "executed" if sent else "already_executed"
                decision.executed_at = datetime.now(timezone.utc)
                decision.outcome = {"message_id": str(sent.id) if sent else None, "delivered": bool(sent)}
                delivered += int(sent is not None)
            except DomainError as exc:
                decision.status = "failed"
                decision.outcome = {"error": exc.detail}
            db.commit()
        return delivered

    @staticmethod
    def _question_followup_text(question: ConversationQuestion | None) -> str:
        """Build a fresh, concise prompt instead of quoting a formatted Teams post."""
        prompts = {
            "owner": "Just checking in: who should I follow up with about this blocker?",
            "eta": "Just checking in: when do you expect this to be ready?",
            "completion": "Just checking in: has this been completed?",
            "work": "Just checking in: could you share a brief work update?",
            "issue": "Just checking in: could you share the current blocker?",
            "outcome": "Just checking in: what was the outcome?",
        }
        return prompts.get(
            question.awaiting_field if question is not None else None,
            "Just checking in: could you share the requested update?",
        )
