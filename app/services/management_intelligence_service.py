from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.intelligence import IntelligenceCycleResult
from app.services.management_decision_service import ManagementDecisionService
from app.services.risk_intelligence_service import RiskIntelligenceService


class ManagementIntelligenceService:
    @staticmethod
    def run(db: Session, *, as_of: datetime | None = None) -> IntelligenceCycleResult:
        risks = RiskIntelligenceService.evaluate(db, as_of=as_of)
        decisions = ManagementDecisionService.decide(db, as_of=as_of)
        return IntelligenceCycleResult(
            risks_evaluated=len(risks), active_risks=len(risks), decisions_created=len(decisions),
            no_action=sum(item.action == "NO_ACTION" for item in decisions),
        )

