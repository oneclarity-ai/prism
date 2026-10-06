"""Evidence-backed organisational memory.  It never replaces operational tables."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import (
    ActivityEventType,
    BlockerStatus,
    CommitmentStatus,
    ManagementProcedureStatus,
    MemoryFactStatus,
    VisibilityScope,
)
from app.models.memory import (
    ActivityEvent,
    ManagementProcedure,
    MemoryEpisode,
    MemoryEvidenceLink,
    MemoryFact,
    MemoryRelation,
    MemorySource,
)
from app.models.message import Message
from app.models.task import Task
from app.schemas.memory import CompiledMemoryContext, MemoryFactCreate
from app.services.errors import NotFoundError, RuleViolationError


class MemoryService:
    @staticmethod
    def record_event(db: Session, *, event_type: ActivityEventType, entity_type: str, entity_id: uuid.UUID | None, source_type: str, source_id: uuid.UUID | None, occurred_at: datetime, idempotency_key: str, subject_employee_id: uuid.UUID | None = None, actor_employee_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None, task_id: uuid.UUID | None = None, metadata: dict | None = None) -> ActivityEvent:
        existing = db.scalar(select(ActivityEvent).where(ActivityEvent.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
        event = ActivityEvent(event_type=event_type, entity_type=entity_type, entity_id=entity_id, source_type=source_type, source_id=source_id, occurred_at=occurred_at, subject_employee_id=subject_employee_id, actor_employee_id=actor_employee_id, project_id=project_id, task_id=task_id, metadata_json=metadata, idempotency_key=idempotency_key)
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def record_transition(
        db: Session,
        *,
        event_type: ActivityEventType,
        entity_type: str,
        entity_id: uuid.UUID,
        previous: dict | None,
        current: dict | None,
        subject_employee_id: uuid.UUID | None = None,
        actor_employee_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        reason: str | None = None,
        occurred_at: datetime | None = None,
    ) -> ActivityEvent:
        """Append one management-relevant before/after event.

        Operational tables intentionally remain the current-state view. This
        event captures the information needed to understand a meaningful change
        without starting the deferred, broader temporal-memory architecture.
        """

        metadata = {"previous": MemoryService._json_value(previous), "new": MemoryService._json_value(current)}
        if reason:
            metadata["reason"] = reason
        if actor_employee_id is None:
            metadata["actor"] = "operator_or_system"
        return MemoryService.record_event(
            db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source_type=entity_type,
            source_id=entity_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            subject_employee_id=subject_employee_id,
            actor_employee_id=actor_employee_id,
            project_id=project_id,
            task_id=task_id,
            metadata=metadata,
            idempotency_key="{}:{}:{}".format(event_type.value, entity_id, uuid.uuid4()),
        )

    @staticmethod
    def record_message_evidence(db: Session, message: Message) -> ActivityEvent:
        event_type = ActivityEventType.MESSAGE_RECEIVED if message.direction.value == "inbound" else ActivityEventType.MESSAGE_SENT
        occurred_at = message.external_created_at or message.created_at or datetime.now(timezone.utc)
        event = MemoryService.record_event(db, event_type=event_type, entity_type="message", entity_id=message.id, source_type="message", source_id=message.id, occurred_at=occurred_at, subject_employee_id=message.employee_id, idempotency_key="{}:{}".format(event_type.value, message.id))
        MemoryService._source(db, source_type="message", source_id=message.id, message=message, event=event)
        return event

    @staticmethod
    def record_daily_update_event(db: Session, daily_update: object) -> ActivityEvent:
        """Write a durable event after a canonical daily update is saved."""
        return MemoryService.record_event(
            db,
            event_type=ActivityEventType.DAILY_UPDATE_CREATED,
            entity_type="daily_update",
            entity_id=daily_update.id,
            source_type="daily_update",
            source_id=daily_update.id,
            occurred_at=daily_update.created_at or datetime.now(timezone.utc),
            subject_employee_id=daily_update.employee_id,
            idempotency_key="daily-update-received:{}".format(daily_update.id),
        )

    @staticmethod
    def _json_value(value: object) -> object:
        if isinstance(value, dict):
            return {str(key): MemoryService._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [MemoryService._json_value(item) for item in value]
        if isinstance(value, (uuid.UUID, datetime, date, Enum)):
            return value.isoformat() if isinstance(value, (datetime, date)) else str(value.value if isinstance(value, Enum) else value)
        return value

    @staticmethod
    def create_fact(db: Session, data: MemoryFactCreate) -> MemoryFact:
        """Create a validated fact, superseding only an equivalent current fact."""
        existing = db.scalar(select(MemoryFact).where(MemoryFact.subject_type == data.subject_type, MemoryFact.subject_id == data.subject_id, MemoryFact.predicate == data.predicate, MemoryFact.object_type == data.object_type, MemoryFact.object_id == data.object_id, MemoryFact.object_text == data.object_text, MemoryFact.status == MemoryFactStatus.CURRENT).limit(1))
        if existing is not None:
            if data.source_type and data.source_id:
                MemoryService._link_fact_source(db, existing, data.source_type, data.source_id)
            return existing
        prior = db.scalar(select(MemoryFact).where(MemoryFact.subject_type == data.subject_type, MemoryFact.subject_id == data.subject_id, MemoryFact.predicate == data.predicate, MemoryFact.status == MemoryFactStatus.CURRENT).order_by(MemoryFact.observed_at.desc()).limit(1))
        fact = MemoryFact(**data.model_dump(exclude={"source_type", "source_id"}), status=MemoryFactStatus.CURRENT)
        if prior is not None and (
            prior.object_type,
            prior.object_id,
            prior.object_text,
        ) != (
            data.object_type,
            data.object_id,
            data.object_text,
        ):
            prior.status = MemoryFactStatus.SUPERSEDED
            prior.valid_until = data.valid_from or data.observed_at
            fact.supersedes_fact_id = prior.id
        db.add(fact)
        db.flush()
        if data.source_type and data.source_id:
            MemoryService._link_fact_source(db, fact, data.source_type, data.source_id)
        return fact

    @staticmethod
    def compile_context(db: Session, employee_id: uuid.UUID, *, viewer_is_manager: bool = True) -> CompiledMemoryContext:
        settings = get_settings()
        employee = db.get(Employee, employee_id)
        if employee is None:
            return CompiledMemoryContext(employee_id=employee_id, uncertainties=["Employee record was not found."])
        tasks = list(db.scalars(select(Task).where(Task.owner_id == employee_id).order_by(Task.updated_at.desc()).limit(5)))
        blockers = list(db.scalars(select(Blocker).where(Blocker.blocked_employee_id == employee_id, Blocker.status == BlockerStatus.OPEN).limit(5)))
        commitments = list(db.scalars(select(Commitment).where(Commitment.employee_id == employee_id, Commitment.status == CommitmentStatus.OPEN).order_by(Commitment.deadline).limit(5)))
        scopes = [VisibilityScope.PROJECT, VisibilityScope.TEAM, VisibilityScope.ORGANISATION, VisibilityScope.MANAGER_ONLY] if viewer_is_manager else [VisibilityScope.PROJECT, VisibilityScope.TEAM, VisibilityScope.ORGANISATION]
        fact_filter = or_(MemoryFact.visibility_scope.in_(scopes), (MemoryFact.visibility_scope == VisibilityScope.PRIVATE_1TO1) & (MemoryFact.subject_id == employee_id))
        facts = list(db.scalars(select(MemoryFact).where(fact_filter, MemoryFact.status == MemoryFactStatus.CURRENT, or_(MemoryFact.subject_id == employee_id, MemoryFact.object_id == employee_id)).order_by(MemoryFact.importance.desc(), MemoryFact.observed_at.desc()).limit(settings.memory_context_max_facts)))
        episodes = list(
            db.scalars(
                select(MemoryEpisode)
                .where(
                    MemoryEpisode.visibility_scope.in_(scopes),
                    MemoryEpisode.primary_employee_id == employee_id,
                )
                .order_by(MemoryEpisode.started_at.desc(), MemoryEpisode.importance.desc())
                .limit(settings.memory_context_max_episodes)
            )
        )
        relations = list(db.scalars(select(MemoryRelation).where(MemoryRelation.status == MemoryFactStatus.CURRENT, or_(MemoryRelation.source_entity_id == employee_id, MemoryRelation.target_entity_id == employee_id), MemoryRelation.visibility_scope.in_(scopes)).order_by(MemoryRelation.importance.desc()).limit(settings.memory_context_max_relations)))
        evidence = list(db.scalars(select(Message).where(Message.employee_id == employee_id).order_by(Message.created_at.desc()).limit(settings.memory_context_max_evidence)))
        return CompiledMemoryContext(employee_id=employee_id, current_work=[task.title for task in tasks], current_blockers=[blocker.description for blocker in blockers], open_commitments=["{} — due {}".format(commitment.description, commitment.deadline.isoformat()) for commitment in commitments], relevant_facts=["{} {} {}".format(f.subject_text or f.subject_type, f.predicate.value, f.object_text or f.object_type or "").strip() for f in facts], relevant_episodes=["{}: {}".format(episode.title, episode.summary) for episode in episodes], relevant_relations=["{} {} {}".format(relation.source_entity_type, relation.relation_type.value, relation.target_entity_type) for relation in relations], raw_evidence=["Message {}: {}".format(message.id, message.content[:500]) for message in evidence])

    @staticmethod
    def approve_procedure(
        db: Session, procedure_id: uuid.UUID, approved_by: uuid.UUID
    ) -> ManagementProcedure:
        procedure = db.get(ManagementProcedure, procedure_id)
        if procedure is None:
            raise NotFoundError("Management procedure was not found")
        if procedure.status != ManagementProcedureStatus.CANDIDATE:
            raise RuleViolationError("Only candidate procedures can be approved")
        approver = db.get(Employee, approved_by)
        if approver is None or not approver.is_active:
            raise RuleViolationError("The approving employee must be active")
        procedure.status = ManagementProcedureStatus.APPROVED
        procedure.approved_by = approver.id
        procedure.approved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(procedure)
        return procedure

    @staticmethod
    def reject_procedure(
        db: Session, procedure_id: uuid.UUID, approved_by: uuid.UUID
    ) -> ManagementProcedure:
        procedure = db.get(ManagementProcedure, procedure_id)
        if procedure is None:
            raise NotFoundError("Management procedure was not found")
        if procedure.status != ManagementProcedureStatus.CANDIDATE:
            raise RuleViolationError("Only candidate procedures can be rejected")
        approver = db.get(Employee, approved_by)
        if approver is None or not approver.is_active:
            raise RuleViolationError("The rejecting employee must be active")
        procedure.status = ManagementProcedureStatus.REJECTED
        procedure.approved_by = approver.id
        procedure.rejected_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(procedure)
        return procedure

    @staticmethod
    def _source(db: Session, *, source_type: str, source_id: uuid.UUID, message: Message | None = None, event: ActivityEvent | None = None) -> MemorySource:
        source = db.scalar(select(MemorySource).where(MemorySource.source_type == source_type, MemorySource.source_id == source_id))
        if source is None:
            source = MemorySource(source_type=source_type, source_id=source_id, conversation_id=message.conversation_id if message else None, message_id=message.id if message else None, activity_event_id=event.id if event else None)
            db.add(source)
            db.flush()
        return source

    @staticmethod
    def link_memory_to_source(
        db: Session,
        *,
        memory_kind: str,
        memory_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        event: ActivityEvent | None = None,
    ) -> None:
        source = MemoryService._source(
            db, source_type=source_type, source_id=source_id, event=event
        )
        exists = db.scalar(
            select(MemoryEvidenceLink.id).where(
                MemoryEvidenceLink.memory_kind == memory_kind,
                MemoryEvidenceLink.memory_id == memory_id,
                MemoryEvidenceLink.memory_source_id == source.id,
            )
        )
        if exists is None:
            db.add(
                MemoryEvidenceLink(
                    memory_kind=memory_kind,
                    memory_id=memory_id,
                    memory_source_id=source.id,
                )
            )

    @staticmethod
    def _link_fact_source(db: Session, fact: MemoryFact, source_type: str, source_id: uuid.UUID) -> None:
        MemoryService.link_memory_to_source(
            db,
            memory_kind="fact",
            memory_id=fact.id,
            source_type=source_type,
            source_id=source_id,
        )
