"""Deterministic, asynchronous consolidation of operational events into memory.

This deliberately does not call an LLM.  It turns only explicit, validated
domain changes into provenance-linked facts, relations, and episodes.  A later
candidate extraction stage can propose richer memories for manager review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.daily_update import DailyUpdate
from app.models.enums import (
    ActivityEventType,
    BlockerSeverity,
    MemoryEpisodeType,
    MemoryFactStatus,
    MemoryJobStatus,
    MemoryPredicate,
    VisibilityScope,
)
from app.models.escalation import Escalation
from app.models.memory import (
    ActivityEvent,
    MemoryEpisode,
    MemoryEvidenceLink,
    MemoryFact,
    MemoryJob,
    MemoryRelation,
    MemorySource,
)
from app.schemas.memory import MemoryFactCreate
from app.services.memory_service import MemoryService


class MemoryConsolidationService:
    """Processes each event once, with a database-backed job record."""

    JOB_TYPE = "deterministic_event_consolidation"

    @staticmethod
    def run(db: Session, *, limit: int = 100, retry_failed: bool = False) -> dict[str, int]:
        statuses = [MemoryJobStatus.PENDING]
        if retry_failed:
            statuses.append(MemoryJobStatus.FAILED)
        event_ids = list(
            db.scalars(
                select(ActivityEvent.id)
                .where(ActivityEvent.processing_status.in_(statuses))
                .order_by(ActivityEvent.occurred_at, ActivityEvent.id)
                .limit(limit)
            )
        )
        result = {"processed": 0, "failed": 0, "facts": 0, "episodes": 0, "relations": 0}
        for event_id in event_ids:
            outcome = MemoryConsolidationService._process_one(db, event_id)
            for key, value in outcome.items():
                result[key] += value
        return result

    @staticmethod
    def run_if_due(db: Session, local_now: datetime) -> dict[str, int]:
        """Run during the configured local-time window; jobs make retries safe."""
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.memory_consolidation_enabled:
            return {"processed": 0, "failed": 0, "facts": 0, "episodes": 0, "relations": 0}
        try:
            hour, minute = (
                int(value) for value in settings.memory_consolidation_time.split(":", 1)
            )
        except ValueError:
            return {"processed": 0, "failed": 0, "facts": 0, "episodes": 0, "relations": 0}
        scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not scheduled <= local_now < scheduled + timedelta(minutes=10):
            return {"processed": 0, "failed": 0, "facts": 0, "episodes": 0, "relations": 0}
        return MemoryConsolidationService.run(db)

    @staticmethod
    def _process_one(db: Session, event_id: object) -> dict[str, int]:
        empty = {"processed": 0, "failed": 0, "facts": 0, "episodes": 0, "relations": 0}
        event = db.get(ActivityEvent, event_id)
        if event is None or event.processing_status == MemoryJobStatus.COMPLETED:
            return empty
        job = db.scalar(
            select(MemoryJob).where(
                MemoryJob.job_type == MemoryConsolidationService.JOB_TYPE,
                MemoryJob.source_id == event.id,
            )
        )
        if job is not None and job.status == MemoryJobStatus.COMPLETED:
            event.processing_status = MemoryJobStatus.COMPLETED
            db.commit()
            return empty
        if job is None:
            job = MemoryJob(
                job_type=MemoryConsolidationService.JOB_TYPE,
                source_id=event.id,
            )
            db.add(job)
        job.status = MemoryJobStatus.PROCESSING
        # SQLAlchemy's column default is applied at INSERT/flush time, while
        # this first increment happens before that flush.
        job.attempt_count = (job.attempt_count or 0) + 1
        job.started_at = datetime.now(timezone.utc)
        event.processing_status = MemoryJobStatus.PROCESSING
        try:
            derived = MemoryConsolidationService._derive(db, event)
            event.processing_status = MemoryJobStatus.COMPLETED
            job.status = MemoryJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.last_error = None
            db.commit()
            derived["processed"] = 1
            derived["failed"] = 0
            return derived
        except Exception as exc:
            db.rollback()
            event = db.get(ActivityEvent, event_id)
            if event is not None:
                event.processing_status = MemoryJobStatus.FAILED
            job = db.scalar(
                select(MemoryJob).where(
                    MemoryJob.job_type == MemoryConsolidationService.JOB_TYPE,
                    MemoryJob.source_id == event_id,
                )
            )
            if job is not None:
                job.status = MemoryJobStatus.FAILED
                job.last_error = str(exc)[:2000]
            db.commit()
            return {"processed": 0, "failed": 1, "facts": 0, "episodes": 0, "relations": 0}

    @staticmethod
    def _derive(db: Session, event: ActivityEvent) -> dict[str, int]:
        result = {"facts": 0, "episodes": 0, "relations": 0}
        if event.event_type == ActivityEventType.BLOCKER_CREATED:
            result = MemoryConsolidationService._blocker_created(db, event)
        elif event.event_type == ActivityEventType.BLOCKER_RESOLVED:
            result = MemoryConsolidationService._blocker_resolved(db, event)
        elif event.event_type in {
            ActivityEventType.DAILY_UPDATE_RECEIVED,
            ActivityEventType.DAILY_UPDATE_CREATED,
            ActivityEventType.DAILY_UPDATE_CHANGED,
        }:
            result = MemoryConsolidationService._daily_update_received(db, event)
        elif event.event_type in {
            ActivityEventType.COMMITMENT_CREATED,
            ActivityEventType.COMMITMENT_COMPLETED,
            ActivityEventType.COMMITMENT_MISSED,
            ActivityEventType.COMMITMENT_REVISED,
        }:
            result = MemoryConsolidationService._commitment_event(db, event)
        elif event.event_type in {
            ActivityEventType.ESCALATION_CREATED,
            ActivityEventType.ESCALATION_RESOLVED,
        }:
            result = MemoryConsolidationService._escalation_event(db, event)
        return result

    @staticmethod
    def _blocker_created(db: Session, event: ActivityEvent) -> dict[str, int]:
        blocker = db.get(Blocker, event.entity_id)
        if blocker is None:
            return {"facts": 0, "episodes": 0, "relations": 0}
        employee = blocker.blocked_employee
        fact = MemoryService.create_fact(
            db,
            MemoryFactCreate(
                subject_type="blocker",
                subject_id=blocker.id,
                subject_text=blocker.description,
                predicate=MemoryPredicate.AFFECTS,
                object_type="employee",
                object_id=blocker.blocked_employee_id,
                object_text=employee.name if employee else None,
                observed_at=event.occurred_at,
                valid_from=event.occurred_at,
                importance=90
                if blocker.severity in {BlockerSeverity.HIGH, BlockerSeverity.CRITICAL}
                else 65,
                visibility_scope=VisibilityScope.MANAGER_ONLY,
                source_type="blocker",
                source_id=blocker.id,
            ),
        )
        episode = MemoryEpisode(
            episode_type=MemoryEpisodeType.BLOCKER,
            title="Blocker: {}".format(blocker.description[:200]),
            summary="{} is blocked.{}".format(
                employee.name if employee else "An employee",
                " Waiting on {}.".format(blocker.dependency_owner.name)
                if blocker.dependency_owner is not None
                else "",
            ),
            started_at=event.occurred_at,
            importance=90
            if blocker.severity in {BlockerSeverity.HIGH, BlockerSeverity.CRITICAL}
            else 65,
            primary_employee_id=blocker.blocked_employee_id,
            visibility_scope=VisibilityScope.MANAGER_ONLY,
            extractor_version="deterministic-v1",
        )
        db.add(episode)
        db.flush()
        MemoryService.link_memory_to_source(
            db,
            memory_kind="episode",
            memory_id=episode.id,
            source_type="blocker",
            source_id=blocker.id,
            event=event,
        )
        if blocker.dependency_owner_id is not None:
            relation = MemoryRelation(
                source_entity_type="employee",
                source_entity_id=blocker.blocked_employee_id,
                relation_type=MemoryPredicate.DEPENDS_ON,
                target_entity_type="employee",
                target_entity_id=blocker.dependency_owner_id,
                valid_from=event.occurred_at,
                confidence=100,
                importance=75,
                visibility_scope=VisibilityScope.MANAGER_ONLY,
            )
            db.add(relation)
            db.flush()
            MemoryService.link_memory_to_source(
                db,
                memory_kind="relation",
                memory_id=relation.id,
                source_type="blocker",
                source_id=blocker.id,
                event=event,
            )
            relations = 1
        else:
            relations = 0
        return {"facts": int(fact is not None), "episodes": 1, "relations": relations}

    @staticmethod
    def _blocker_resolved(db: Session, event: ActivityEvent) -> dict[str, int]:
        blocker = db.get(Blocker, event.entity_id)
        if blocker is None:
            return {"facts": 0, "episodes": 0, "relations": 0}
        source = db.scalar(
            select(MemorySource).where(
                MemorySource.source_type == "blocker", MemorySource.source_id == blocker.id
            )
        )
        if source is not None:
            affected_fact_ids = select(MemoryEvidenceLink.memory_id).where(
                MemoryEvidenceLink.memory_kind == "fact",
                MemoryEvidenceLink.memory_source_id == source.id,
            )
            for fact in db.scalars(
                select(MemoryFact).where(
                    MemoryFact.id.in_(affected_fact_ids),
                    MemoryFact.status == MemoryFactStatus.CURRENT,
                )
            ):
                fact.status = MemoryFactStatus.EXPIRED
                fact.valid_until = event.occurred_at
            affected_relation_ids = select(MemoryEvidenceLink.memory_id).where(
                MemoryEvidenceLink.memory_kind == "relation",
                MemoryEvidenceLink.memory_source_id == source.id,
            )
            for relation in db.scalars(
                select(MemoryRelation).where(
                    MemoryRelation.id.in_(affected_relation_ids),
                    MemoryRelation.status == MemoryFactStatus.CURRENT,
                )
            ):
                relation.status = MemoryFactStatus.EXPIRED
                relation.valid_until = event.occurred_at
        episode = MemoryEpisode(
            episode_type=MemoryEpisodeType.RESOLUTION,
            title="Resolved: {}".format(blocker.description[:200]),
            summary="The blocker for {} was resolved.".format(
                blocker.blocked_employee.name if blocker.blocked_employee else "the employee"
            ),
            started_at=event.occurred_at,
            ended_at=event.occurred_at,
            importance=70,
            primary_employee_id=blocker.blocked_employee_id,
            visibility_scope=VisibilityScope.MANAGER_ONLY,
            extractor_version="deterministic-v1",
        )
        db.add(episode)
        db.flush()
        MemoryService.link_memory_to_source(
            db,
            memory_kind="episode",
            memory_id=episode.id,
            source_type="blocker",
            source_id=blocker.id,
            event=event,
        )
        return {"facts": 0, "episodes": 1, "relations": 0}

    @staticmethod
    def _daily_update_received(db: Session, event: ActivityEvent) -> dict[str, int]:
        update = db.get(DailyUpdate, event.entity_id)
        if update is None or not update.today_summary:
            return {"facts": 0, "episodes": 0, "relations": 0}
        fact = MemoryService.create_fact(
            db,
            MemoryFactCreate(
                subject_type="employee",
                subject_id=update.employee_id,
                subject_text=update.employee.name if update.employee else None,
                predicate=MemoryPredicate.WORKING_ON,
                object_type="daily_update",
                object_id=update.id,
                object_text=update.today_summary,
                observed_at=event.occurred_at,
                valid_from=event.occurred_at,
                importance=40,
                visibility_scope=VisibilityScope.MANAGER_ONLY,
                source_type="daily_update",
                source_id=update.id,
            ),
        )
        return {"facts": int(fact is not None), "episodes": 0, "relations": 0}

    @staticmethod
    def _commitment_event(db: Session, event: ActivityEvent) -> dict[str, int]:
        commitment = db.get(Commitment, event.entity_id)
        if commitment is None:
            return {"facts": 0, "episodes": 0, "relations": 0}
        labels = {
            ActivityEventType.COMMITMENT_CREATED: "Commitment made",
            ActivityEventType.COMMITMENT_COMPLETED: "Commitment completed",
            ActivityEventType.COMMITMENT_MISSED: "Commitment missed",
            ActivityEventType.COMMITMENT_REVISED: "Commitment revised",
        }
        episode = MemoryEpisode(
            episode_type=MemoryEpisodeType.DELIVERY,
            title="{}: {}".format(labels[event.event_type], commitment.description[:190]),
            summary="{}: {}.".format(
                commitment.employee.name if commitment.employee else "An employee",
                labels[event.event_type].lower(),
            ),
            started_at=event.occurred_at,
            importance=80 if event.event_type == ActivityEventType.COMMITMENT_MISSED else 55,
            primary_employee_id=commitment.employee_id,
            visibility_scope=VisibilityScope.MANAGER_ONLY,
            extractor_version="deterministic-v1",
        )
        db.add(episode)
        db.flush()
        MemoryService.link_memory_to_source(
            db,
            memory_kind="episode",
            memory_id=episode.id,
            source_type="commitment",
            source_id=commitment.id,
            event=event,
        )
        return {"facts": 0, "episodes": 1, "relations": 0}

    @staticmethod
    def _escalation_event(db: Session, event: ActivityEvent) -> dict[str, int]:
        escalation = db.get(Escalation, event.entity_id)
        if escalation is None:
            return {"facts": 0, "episodes": 0, "relations": 0}
        resolved = event.event_type == ActivityEventType.ESCALATION_RESOLVED
        episode = MemoryEpisode(
            episode_type=MemoryEpisodeType.DECISION,
            title="{}: {}".format(
                "Escalation resolved" if resolved else "Escalation raised", escalation.reason[:190]
            ),
            summary=escalation.context or escalation.reason,
            started_at=event.occurred_at,
            ended_at=event.occurred_at if resolved else None,
            importance=90 if escalation.requires_manager_approval else 70,
            project_id=escalation.project_id,
            primary_employee_id=escalation.employee_id,
            visibility_scope=VisibilityScope.MANAGER_ONLY,
            extractor_version="deterministic-v1",
        )
        db.add(episode)
        db.flush()
        MemoryService.link_memory_to_source(
            db,
            memory_kind="episode",
            memory_id=episode.id,
            source_type="escalation",
            source_id=escalation.id,
            event=event,
        )
        return {"facts": 0, "episodes": 1, "relations": 0}
