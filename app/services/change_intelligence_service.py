"""Structured answers to what changed, without replaying raw conversations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.memory import ActivityEvent
from app.schemas.intelligence import ChangeRead


class ChangeIntelligenceService:
    @staticmethod
    def changes(
        db: Session,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        employee_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[ChangeRead]:
        since = since or datetime.now(timezone.utc) - timedelta(days=1)
        until = until or datetime.now(timezone.utc)
        query = select(ActivityEvent).where(
            ActivityEvent.occurred_at >= since,
            ActivityEvent.occurred_at <= until,
        )
        if employee_id:
            query = query.where(
                or_(
                    ActivityEvent.subject_employee_id == employee_id,
                    ActivityEvent.actor_employee_id == employee_id,
                )
            )
        if project_id:
            query = query.where(ActivityEvent.project_id == project_id)
        if entity_type:
            query = query.where(ActivityEvent.entity_type == entity_type)
        events = list(db.scalars(query.order_by(ActivityEvent.occurred_at.desc()).limit(limit)))
        return [ChangeIntelligenceService._read(event) for event in events]

    @staticmethod
    def _read(event: ActivityEvent) -> ChangeRead:
        metadata = event.metadata_json or {}
        reason = metadata.get("reason")
        summary = event.event_type.value.replace("_", " ")
        if reason:
            summary += f": {reason}"
        return ChangeRead(
            event_id=event.id,
            event_type=event.event_type.value,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            employee_id=event.subject_employee_id,
            project_id=event.project_id,
            task_id=event.task_id,
            occurred_at=event.occurred_at,
            summary=summary,
            previous=metadata.get("previous"),
            current=metadata.get("new"),
            evidence=[f"event:{event.id}"]
            + ([f"{event.source_type}:{event.source_id}"] if event.source_id else []),
        )
