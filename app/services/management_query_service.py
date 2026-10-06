"""Deterministic natural-language routing over structured organisational state."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import BlockerStatus, CommitmentStatus
from app.models.intelligence import ManagementDecision, ManagementRisk
from app.models.project import Project
from app.schemas.intelligence import ManagementQueryAnswer
from app.services.attention_queue_service import AttentionQueueService
from app.services.change_intelligence_service import ChangeIntelligenceService
from app.services.dependency_graph_service import DependencyGraphService
from app.services.management_state_service import ManagementStateService
from app.services.journey_service import JourneyService


class ManagementQueryService:
    @staticmethod
    def answer(db: Session, question: str, *, as_of: datetime | None = None) -> ManagementQueryAnswer:
        now = as_of or datetime.now(timezone.utc)
        folded = question.casefold().strip()
        employee = ManagementQueryService._mentioned_employee(db, folded)
        project = ManagementQueryService._mentioned_project(db, folded)

        if "what needs my attention" in folded or "needs attention" in folded:
            items = AttentionQueueService.list(db)
            return ManagementQueryAnswer(
                answer=f"{len(items)} item(s) currently need management attention.", answer_type="attention",
                items=[item.model_dump(mode="json") for item in items],
                evidence=[f"risk:{item.risk.id}" for item in items],
            )
        if "what changed" in folded or "deadlines moved" in folded or "blockers are new" in folded:
            since = now - timedelta(days=7 if "week" in folded else 1)
            changes = ChangeIntelligenceService.changes(
                db, since=since, employee_id=employee.id if employee else None,
                entity_type="commitment" if "commitment" in folded else None,
            )
            return ManagementQueryAnswer(
                answer=f"{len(changes)} relevant change(s) were recorded.", answer_type="changes",
                items=[item.model_dump(mode="json") for item in changes],
                evidence=[f"event:{item.event_id}" for item in changes],
            )
        if employee and ("promise" in folded or "commitment" in folded):
            since = now - timedelta(days=7 if "week" in folded else 30)
            commitments = list(db.scalars(select(Commitment).where(
                Commitment.employee_id == employee.id,
                Commitment.committed_at >= since,
            ).order_by(Commitment.committed_at.desc())))
            return ManagementQueryAnswer(
                answer=f"{employee.name} made {len(commitments)} commitment(s) in that period.",
                answer_type="commitments",
                items=[{"id": str(item.id), "description": item.description,
                        "deadline": item.deadline.isoformat(), "status": item.status.value,
                        "revised_from_id": str(item.revised_from_id) if item.revised_from_id else None}
                       for item in commitments],
                evidence=[f"commitment:{item.id}" for item in commitments],
            )
        if employee and ("why" in folded and "blocked" in folded):
            blockers = list(db.scalars(select(Blocker).where(
                Blocker.blocked_employee_id == employee.id,
                Blocker.status == BlockerStatus.OPEN,
            )))
            return ManagementQueryAnswer(
                answer=f"{employee.name} has {len(blockers)} open blocker(s).",
                answer_type="blockers",
                items=[{"id": str(item.id), "description": item.description,
                        "owner_ids": [str(value) for value in item.dependency_owner_ids]}
                       for item in blockers],
                evidence=[f"blocker:{item.id}" for item in blockers],
            )
        if "what did the agent do" in folded or "agent do about" in folded:
            decisions = list(db.scalars(select(ManagementDecision).order_by(
                ManagementDecision.decided_at.desc()
            ).limit(20)))
            return ManagementQueryAnswer(
                answer=f"The agent recorded {len(decisions)} recent management decision(s).",
                answer_type="agent_actions",
                items=[{"id": str(item.id), "action": item.action, "status": item.status,
                        "reason": item.reason, "outcome": item.outcome} for item in decisions],
                evidence=[f"decision:{item.id}" for item in decisions],
            )
        if "journey" in folded:
            journeys = JourneyService.list(db, limit=20)
            return ManagementQueryAnswer(
                answer=f"{len(journeys)} recent blocker journey/journeys are available.",
                answer_type="journeys",
                items=[item.model_dump(mode="json") for item in journeys],
                evidence=[f"blocker:{item.blocker_id}" for item in journeys],
            )
        if "what could affect" in folded or "at risk" in folded:
            risks = list(db.scalars(select(ManagementRisk).where(
                ManagementRisk.status == "active"
            ).order_by(ManagementRisk.last_evaluated_at.desc())))
            if project:
                task_ids = {task.id for task in project.tasks}
                risks = [risk for risk in risks if any(
                    entity.get("id") in {str(project.id), *(str(value) for value in task_ids)}
                    for entity in risk.affected_entities
                )]
            return ManagementQueryAnswer(
                answer=f"{len(risks)} evidence-backed risk signal(s) may affect the requested work.",
                answer_type="risks",
                items=[{"id": str(item.id), "summary": item.summary, "severity": item.severity,
                        "reason": item.reason, "confidence": item.confidence} for item in risks],
                evidence=[value for item in risks for value in item.evidence],
                uncertainty=None if risks else "No supporting risk evidence is currently stored.",
            )
        if employee and ("working on" in folded or folded.startswith("what is")):
            state = ManagementStateService.employee_state(db, employee.id, as_of=now)
            return ManagementQueryAnswer(
                answer=f"{employee.name} has {len(state.active_work)} active work item(s).",
                answer_type="employee_state", items=[state.model_dump(mode="json")],
                evidence=sorted({source for section in [state.active_work, state.current_blockers, state.open_commitments]
                                 for item in section for source in item.evidence}),
            )
        if "who is blocked" in folded:
            blockers = list(db.scalars(select(Blocker).where(Blocker.status == BlockerStatus.OPEN)))
            return ManagementQueryAnswer(
                answer=f"{len(blockers)} open blocker(s).", answer_type="blockers",
                items=[{"blocker_id": str(item.id), "employee": item.blocked_employee.name,
                        "description": item.description} for item in blockers],
                evidence=[f"blocker:{item.id}" for item in blockers],
            )
        if "missed a commitment" in folded or "missed commitment" in folded:
            commitments = list(db.scalars(select(Commitment).where(Commitment.status == CommitmentStatus.MISSED)))
            return ManagementQueryAnswer(
                answer=f"{len(commitments)} missed commitment(s) remain unresolved.", answer_type="commitments",
                items=[{"commitment_id": str(item.id), "employee": item.employee.name,
                        "description": item.description, "deadline": item.deadline.isoformat()} for item in commitments],
                evidence=[f"commitment:{item.id}" for item in commitments],
            )
        if employee and ("who is waiting for" in folded or "what depends on" in folded):
            affected = DependencyGraphService.affected_by(db, "employee", employee.id)
            return ManagementQueryAnswer(
                answer=f"{len(affected)} downstream entity/entities depend on {employee.name}.",
                answer_type="dependency_impact", items=affected,
                evidence=[f"employee:{employee.id}"],
            )
        if employee and ("waiting for" in folded or "waiting on" in folded or "depends on" in folded):
            edges = [edge for edge in DependencyGraphService.edges(db) if edge.source_entity_type == "employee" and edge.source_entity_id == employee.id]
            return ManagementQueryAnswer(
                answer=f"{employee.name} has {len(edges)} active dependency relationship(s).",
                answer_type="dependencies", items=[edge.model_dump(mode="json") for edge in edges],
                evidence=[source for edge in edges for source in edge.evidence],
            )
        return ManagementQueryAnswer(
            answer="I could not map that question to verified structured state.", answer_type="unknown",
            uncertainty="Try asking about attention, blockers, commitments, changes, a person's work, or dependencies.",
        )

    @staticmethod
    def _mentioned_employee(db: Session, folded: str) -> Employee | None:
        matches = []
        for employee in db.scalars(select(Employee).where(Employee.is_active.is_(True))):
            names = [employee.name.casefold(), employee.email.casefold(), employee.name.split()[0].casefold()]
            if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", folded) for name in names):
                matches.append(employee)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _mentioned_project(db: Session, folded: str) -> Project | None:
        matches = [project for project in db.scalars(select(Project)) if re.search(
            r"(?<!\w)" + re.escape(project.name.casefold()) + r"(?!\w)", folded
        )]
        return matches[0] if len(matches) == 1 else None
