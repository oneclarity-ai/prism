from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.intelligence import ManagementDecision, ManagementRisk
from app.schemas.intelligence import AttentionItem, RiskRead


class AttentionQueueService:
    @staticmethod
    def list(db: Session, *, limit: int = 50) -> list[AttentionItem]:
        risks = list(db.scalars(select(ManagementRisk).where(
            ManagementRisk.status == "active",
            ManagementRisk.severity.in_(["attention", "urgent"]),
        ).order_by(ManagementRisk.severity.desc(), ManagementRisk.last_evaluated_at.desc()).limit(limit)))
        result = []
        for risk in risks:
            people = []
            for entity in risk.affected_entities or []:
                if entity.get("type") != "employee" and entity.get("entity_type") != "employee":
                    continue
                try:
                    employee = db.get(Employee, entity.get("id"))
                except (TypeError, ValueError):
                    employee = None
                if employee and employee.name not in people:
                    people.append(employee.name)
            decisions = list(db.scalars(select(ManagementDecision).where(
                ManagementDecision.trigger_id == risk.id
            ).order_by(ManagementDecision.decided_at.desc()).limit(5)))
            result.append(AttentionItem(
                risk=RiskRead.model_validate(risk), people=people,
                impact=risk.summary,
                agent_actions=[f"{item.action}: {item.reason}" for item in decisions],
                current_expectation=(
                    f"Deadline at risk: {risk.deadline_at_risk.isoformat()}"
                    if risk.deadline_at_risk else "A meaningful update or resolution is expected."
                ),
                why_visible=risk.reason,
                manager_options=["Wait for the next useful update", "Review the evidence", "Approve escalation"]
                if risk.severity == "urgent" else ["Wait for the agent follow-up", "Review the evidence"],
            ))
        return result

