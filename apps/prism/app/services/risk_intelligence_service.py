"""Deterministic, explainable risk and silence classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import BlockerSeverity, BlockerStatus, CommitmentStatus
from app.models.intelligence import ManagementRisk
from app.services.dependency_graph_service import DependencyGraphService
from app.services.followup_intelligence_service import FollowUpIntelligenceService


class RiskIntelligenceService:
    @staticmethod
    def evaluate(
        db: Session, *, as_of: datetime | None = None, commit: bool = True
    ) -> list[ManagementRisk]:
        now = as_of or datetime.now(timezone.utc)
        proposals: dict[str, dict] = {}
        managed_ids = set(
            db.scalars(
                select(Employee.id).where(
                    Employee.is_active.is_(True), Employee.is_managed.is_(True)
                )
            )
        )
        for blocker in db.scalars(
            select(Blocker).where(
                Blocker.status == BlockerStatus.OPEN,
                Blocker.blocked_employee_id.in_(managed_ids),
            )
        ):
            age = now - (blocker.created_at or now)
            affected_by_id: dict[tuple[str, str], dict] = {}
            for owner_id in blocker.dependency_owner_ids:
                for entity in DependencyGraphService.affected_by(db, "employee", owner_id):
                    affected_by_id[(entity["entity_type"], entity["id"])] = entity
            affected = list(affected_by_id.values())
            revisions = (
                db.scalar(
                    select(func.count())
                    .select_from(Commitment)
                    .where(
                        Commitment.blocker_id == blocker.id,
                        Commitment.revised_from_id.is_not(None),
                    )
                )
                or 0
            )
            missed = (
                db.scalar(
                    select(func.count())
                    .select_from(Commitment)
                    .where(
                        Commitment.blocker_id == blocker.id,
                        Commitment.status.in_(
                            [CommitmentStatus.MISSED, CommitmentStatus.SUPERSEDED]
                        ),
                    )
                )
                or 0
            )
            score = {
                BlockerSeverity.LOW: 5,
                BlockerSeverity.MEDIUM: 12,
                BlockerSeverity.HIGH: 25,
                BlockerSeverity.CRITICAL: 40,
            }[blocker.severity]
            signals = [f"blocker severity is {blocker.severity.value}"]
            if age >= timedelta(days=1):
                score += 10
                signals.append(f"blocked for {max(1, age.days)} day(s)")
            if age >= timedelta(days=3):
                score += 10
            if affected:
                score += min(25, len(affected) * 5)
                signals.append(f"{len(affected)} downstream entity/entities affected")
            if revisions:
                score += min(20, revisions * 8)
                signals.append(f"ETA revised {revisions} time(s)")
            if missed:
                score += min(25, missed * 12)
                signals.append(f"{missed} missed or superseded commitment(s)")
            severity = RiskIntelligenceService._severity(score)
            if severity == "normal":
                continue
            fingerprint = f"blocker-risk:{blocker.id}"
            proposals[fingerprint] = {
                "fingerprint": fingerprint,
                "risk_type": "dependency_delay",
                "severity": severity,
                "source_entity_type": "blocker",
                "source_entity_id": blocker.id,
                "summary": blocker.description[:500],
                "reason": "; ".join(signals),
                "recommended_action": "FOLLOW_UP"
                if severity in {"watch", "attention"}
                else "REQUEST_MANAGER_APPROVAL",
                "affected_entities": (
                    [{"type": "employee", "id": str(blocker.blocked_employee_id)}] + affected
                ),
                "signals": signals,
                "evidence": [f"blocker:{blocker.id}"]
                + [
                    f"commitment:{item.id}"
                    for item in db.scalars(
                        select(Commitment).where(Commitment.blocker_id == blocker.id)
                    )
                ],
                "deadline_at_risk": blocker.task.deadline if blocker.task else None,
                "confidence": min(0.98, 0.6 + score / 200),
            }

        for candidate in FollowUpIntelligenceService.candidates(db, as_of=now):
            if candidate["kind"] not in {"silent_blocker", "unanswered_question"}:
                continue
            fingerprint = f"silence:{candidate['kind']}:{candidate['id']}"
            proposals[fingerprint] = {
                "fingerprint": fingerprint,
                "risk_type": "silence",
                "severity": "watch",
                "source_entity_type": candidate["kind"],
                "source_entity_id": candidate["id"],
                "summary": "Follow-up may be useful",
                "reason": candidate["reason"],
                "recommended_action": "FOLLOW_UP",
                "affected_entities": candidate["affected"]
                + [{"type": "employee", "id": str(candidate["target_employee_id"])}],
                "signals": ["no recent meaningful state change"],
                "evidence": candidate["evidence"],
                "deadline_at_risk": None,
                "confidence": candidate["confidence"],
            }

        active: list[ManagementRisk] = []
        for fingerprint, data in proposals.items():
            risk = db.scalar(
                select(ManagementRisk).where(ManagementRisk.fingerprint == fingerprint)
            )
            if risk is None:
                risk = ManagementRisk(first_detected_at=now, **data)
                db.add(risk)
            else:
                for field, value in data.items():
                    if field != "fingerprint":
                        setattr(risk, field, value)
                risk.status = "active"
                risk.resolved_at = None
            risk.last_evaluated_at = now
            active.append(risk)

        for risk in db.scalars(select(ManagementRisk).where(ManagementRisk.status == "active")):
            if risk.fingerprint not in proposals:
                risk.status = "resolved"
                risk.resolved_at = now
                risk.last_evaluated_at = now
        if commit:
            db.commit()
            for risk in active:
                db.refresh(risk)
        else:
            db.flush()
        return active

    @staticmethod
    def _severity(score: int) -> str:
        if score >= 65:
            return "urgent"
        if score >= 35:
            return "attention"
        if score >= 15:
            return "watch"
        return "normal"
