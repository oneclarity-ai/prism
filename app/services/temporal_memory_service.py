"""Validity-aware memory retrieval for compact management context."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import MemoryFactStatus
from app.models.memory import MemoryFact, MemoryRelation


class TemporalMemoryService:
    @staticmethod
    def retrieve(
        db: Session,
        *,
        employee_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        issue_id: uuid.UUID | None = None,
        include_history: bool = False,
        limit: int = 12,
        as_of: datetime | None = None,
    ) -> dict[str, list[dict]]:
        now = as_of or datetime.now(timezone.utc)
        entity_ids = {value for value in [employee_id, project_id, issue_id] if value is not None}
        fact_query = select(MemoryFact).where(
            MemoryFact.observed_at <= now,
            or_(MemoryFact.valid_from.is_(None), MemoryFact.valid_from <= now),
        )
        relation_query = select(MemoryRelation).where(
            or_(MemoryRelation.valid_from.is_(None), MemoryRelation.valid_from <= now),
        )
        if not include_history:
            fact_query = fact_query.where(
                MemoryFact.status == MemoryFactStatus.CURRENT,
                or_(MemoryFact.valid_until.is_(None), MemoryFact.valid_until > now),
            )
            relation_query = relation_query.where(
                MemoryRelation.status == MemoryFactStatus.CURRENT,
                or_(MemoryRelation.valid_until.is_(None), MemoryRelation.valid_until > now),
            )
        if entity_ids:
            fact_query = fact_query.where(
                or_(MemoryFact.subject_id.in_(entity_ids), MemoryFact.object_id.in_(entity_ids))
            )
            relation_query = relation_query.where(
                or_(
                    MemoryRelation.source_entity_id.in_(entity_ids),
                    MemoryRelation.target_entity_id.in_(entity_ids),
                )
            )
        facts = list(db.scalars(fact_query.limit(100)))
        relations = list(db.scalars(relation_query.limit(100)))

        def fact_score(fact: MemoryFact) -> float:
            current = 1000 if fact.status == MemoryFactStatus.CURRENT else 0
            valid = 300 if (fact.valid_until is None or fact.valid_until >= now) else -300
            age_days = max(0.0, (now - fact.observed_at).total_seconds() / 86400)
            recency = 200 / (1 + math.log1p(age_days))
            entity = 300 if fact.subject_id in entity_ids or fact.object_id in entity_ids else 0
            return (
                current + valid + recency + entity + fact.importance + (fact.confidence or 50) / 2
            )

        ranked = sorted(facts, key=fact_score, reverse=True)[:limit]
        return {
            "facts": [
                {
                    "id": str(item.id),
                    "subject": item.subject_text or item.subject_type,
                    "predicate": item.predicate.value,
                    "object": item.object_text or item.object_type,
                    "status": item.status.value,
                    "valid_from": item.valid_from.isoformat() if item.valid_from else None,
                    "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                    "confidence": item.confidence,
                    "score": round(fact_score(item), 2),
                }
                for item in ranked
            ],
            "relations": [
                {
                    "id": str(item.id),
                    "source_type": item.source_entity_type,
                    "source_id": str(item.source_entity_id),
                    "relation": item.relation_type.value,
                    "target_type": item.target_entity_type,
                    "target_id": str(item.target_entity_id),
                    "status": item.status.value,
                }
                for item in relations[:limit]
            ],
        }
