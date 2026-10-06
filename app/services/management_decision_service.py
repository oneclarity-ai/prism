"""Allow-listed, policy-validated proactive management decisions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.intelligence import ManagementDecision, ManagementRisk
from app.schemas.intelligence import ProactiveDecisionProposal
from app.services.errors import DomainError
from app.services.followup_intelligence_service import FollowUpIntelligenceService
from app.services.llm_service import LLMService
from app.services.manager_feedback_service import ManagerFeedbackService
from app.services.management_policy import ManagementPolicy
from app.services.microsoft_service import MicrosoftService


class ManagementDecisionService:
    PROACTIVE_PROMPT = """You recommend one bounded management action for one supplied risk.
Use only supplied employee and issue IDs. Prefer NO_ACTION when communication adds no value.
Do not escalate directly; use REQUEST_MANAGER_APPROVAL for protected or genuinely urgent cases.
Return a concise factual reason, not chain-of-thought. Never invent people, work, deadlines, or evidence."""

    ALLOWED_ACTIONS = {
        "NO_ACTION", "ACKNOWLEDGE", "ASK_CLARIFICATION", "FOLLOW_UP",
        "UPDATE_DEPENDENT", "CREATE_COMMITMENT", "UPDATE_COMMITMENT",
        "ESCALATE", "REQUEST_MANAGER_APPROVAL",
    }

    @staticmethod
    def decide(db: Session, *, as_of: datetime | None = None, commit: bool = True) -> list[ManagementDecision]:
        now = as_of or datetime.now(timezone.utc)
        # Follow-up decisions are actionable Teams work, not a backlog replay.
        # Restrict them to people and source records created during the active
        # automation run.  This deliberately leaves historic records visible
        # as history without letting a new run message people about them.
        active_run = MicrosoftService.active_run(db)
        if active_run is None:
            candidates = []
        else:
            target_ids = {uuid.UUID(str(item)) for item in active_run.target_employee_ids or []}
            candidates = FollowUpIntelligenceService.candidates(
                db,
                as_of=now,
                eligible_employee_ids=target_ids,
                not_before=active_run.started_at,
            )
        created: list[ManagementDecision] = []
        for candidate in candidates:
            target = candidate["target_employee_id"]
            action = ManagementPolicy.recommend({
                "overdue_minutes": 121 if candidate["kind"] == "overdue_commitment" else 0,
                "dependent_waiting": bool(candidate["affected"]),
                "silence_hours": 48 if candidate["kind"] == "silent_blocker" else 0,
                "blocked": candidate["kind"] == "silent_blocker",
                "owner_known": True,
                "unanswered_hours": 4 if candidate["kind"] == "unanswered_question" else 0,
                "question_material": True,
            })
            feedback = ManagerFeedbackService.applicable(db, employee_id=target, as_of=now)
            blocking_instruction = next((item for item in feedback if any(
                phrase in item.instruction.casefold() for phrase in [
                    "don't chase", "do not chase", "don't follow up", "do not follow up"
                ]
            )), None)
            reason = candidate["reason"]
            if blocking_instruction:
                action = ManagementPolicy.recommend({"manager_suppressed": True})
                reason = f"Manager preference suppresses follow-up: {blocking_instruction.instruction}"
            key = f"v2:{candidate['kind']}:{candidate['id']}:{action}:{now.date().isoformat()}"
            existing = db.scalar(select(ManagementDecision).where(ManagementDecision.idempotency_key == key))
            if existing:
                created.append(existing)
                continue
            decision = ManagementDecision(
                idempotency_key=key, trigger_type=candidate["kind"], trigger_id=candidate["id"],
                action=action, status="validated", target_employee_ids=[str(target)],
                related_issue_id=candidate["related_issue_id"], reason=reason,
                confidence=candidate["confidence"], evidence=candidate["evidence"],
                context={"affected": candidate["affected"]}, decided_at=now,
            )
            ManagementDecisionService.validate(decision)
            db.add(decision)
            created.append(decision)
            if blocking_instruction and blocking_instruction.scope == "one_time":
                blocking_instruction.is_active = False

        for risk in db.scalars(select(ManagementRisk).where(
            ManagementRisk.status == "active", ManagementRisk.severity.in_(["attention", "urgent"])
        )):
            key = f"v2:risk:{risk.id}:{now.date().isoformat()}"
            if db.scalar(select(ManagementDecision.id).where(ManagementDecision.idempotency_key == key)):
                continue
            action = ManagementPolicy.recommend({
                "urgent_manager_risk": risk.severity == "urgent",
                "overdue_minutes": 121 if risk.recommended_action == "FOLLOW_UP" else 0,
                "dependent_waiting": bool(risk.affected_entities),
            })
            targets = [str(value.get("id")) for value in risk.affected_entities if value.get("type") == "employee"]
            reason, confidence, model = risk.reason, risk.confidence, None
            settings = get_settings()
            if (settings.intelligence_llm_enabled and settings.azure_openai_deployment
                    and settings.azure_openai_endpoint and settings.azure_openai_api_key):
                try:
                    proposal = LLMService.complete(
                        prompt=ManagementDecisionService.PROACTIVE_PROMPT,
                        context={
                            "risk_id": str(risk.id), "risk_type": risk.risk_type,
                            "severity": risk.severity, "summary": risk.summary,
                            "signals": risk.signals, "evidence": risk.evidence,
                            "affected_employee_ids": targets,
                            "deadline_at_risk": risk.deadline_at_risk,
                            "deterministic_recommendation": action,
                        },
                        output_model=ProactiveDecisionProposal,
                        feature="proactive_management_decision",
                    )
                    if not {str(value) for value in proposal.target_employee_ids}.issubset(set(targets)):
                        raise ValueError("The model selected an employee outside supplied evidence")
                    if proposal.related_issue_id not in {None, risk.source_entity_id}:
                        raise ValueError("The model selected an issue outside supplied evidence")
                    if proposal.action in {"FOLLOW_UP", "ACKNOWLEDGE", "ASK_CLARIFICATION", "UPDATE_DEPENDENT"} and not proposal.target_employee_ids:
                        raise ValueError("The model proposed communication without a supplied target")
                    action = proposal.action
                    targets = [str(value) for value in proposal.target_employee_ids]
                    reason, confidence = proposal.reason, proposal.confidence
                    model = settings.azure_openai_deployment
                except (DomainError, ValueError):
                    # Deterministic policy remains the safe fallback.
                    pass
            decision = ManagementDecision(
                idempotency_key=key, trigger_type="management_risk", trigger_id=risk.id,
                action=action, status="validated", target_employee_ids=targets,
                related_issue_id=risk.source_entity_id if risk.source_entity_type == "blocker" else None,
                reason=reason, confidence=confidence, evidence=risk.evidence,
                context={"signals": risk.signals, "severity": risk.severity},
                model=model, decided_at=now,
            )
            ManagementDecisionService.validate(decision)
            db.add(decision)
            created.append(decision)
        if commit:
            db.commit()
            for item in created:
                db.refresh(item)
        else:
            db.flush()
        return created

    @staticmethod
    def validate(decision: ManagementDecision) -> None:
        if decision.action not in ManagementDecisionService.ALLOWED_ACTIONS:
            raise ValueError("Unsupported management action")
        if decision.action in {"FOLLOW_UP", "ACKNOWLEDGE", "ASK_CLARIFICATION", "UPDATE_DEPENDENT"} and not decision.target_employee_ids:
            raise ValueError("Communication decisions require an existing target employee")
        if decision.action == "FOLLOW_UP" and not decision.evidence:
            raise ValueError("A follow-up requires source evidence")
        if decision.action == "ESCALATE":
            raise ValueError("Automatic escalation is not allowed; request manager approval")
