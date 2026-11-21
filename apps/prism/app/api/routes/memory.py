from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import MemoryFactStatus, VisibilityScope
from app.models.memory import (
    ActivityEvent,
    ManagementProcedure,
    MemoryEpisode,
    MemoryEvidenceLink,
    MemoryFact,
    MemoryRelation,
    MemorySource,
)
from app.schemas.common import Page
from app.schemas.memory import (
    ActivityEventRead,
    CompiledMemoryContext,
    ManagementProcedureRead,
    MemoryFactCreate,
    MemoryFactRead,
    MemorySearchRead,
    ProcedureDecision,
)
from app.services.memory_backfill_service import MemoryBackfillService
from app.services.memory_consolidation_service import MemoryConsolidationService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/v1/memory", tags=["organisational memory"])


@router.get("/facts", response_model=Page[MemoryFactRead])
def facts(
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    status_filter: Optional[MemoryFactStatus] = Query(default=None, alias="status"),
    visibility: Optional[VisibilityScope] = None,
    observed_from: Optional[datetime] = None,
    observed_to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    statement = select(MemoryFact)
    count_statement = select(func.count()).select_from(MemoryFact)
    if employee_id is not None:
        condition = or_(MemoryFact.subject_id == employee_id, MemoryFact.object_id == employee_id)
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    for column, value in [
        (MemoryFact.status, status_filter),
        (MemoryFact.visibility_scope, visibility),
    ]:
        if value is not None:
            statement = statement.where(column == value)
            count_statement = count_statement.where(column == value)
    if observed_from is not None:
        statement = statement.where(MemoryFact.observed_at >= observed_from)
        count_statement = count_statement.where(MemoryFact.observed_at >= observed_from)
    if observed_to is not None:
        statement = statement.where(MemoryFact.observed_at <= observed_to)
        count_statement = count_statement.where(MemoryFact.observed_at <= observed_to)
    items = list(
        db.scalars(statement.order_by(MemoryFact.observed_at.desc()).limit(limit).offset(offset))
    )
    return Page(items=items, total=db.scalar(count_statement) or 0, limit=limit, offset=offset)


@router.post("/facts", response_model=MemoryFactRead, status_code=status.HTTP_201_CREATED)
def create_fact(payload: MemoryFactCreate, db: Session = Depends(get_db)):
    fact = MemoryService.create_fact(db, payload)
    db.commit()
    db.refresh(fact)
    return fact


@router.get("/episodes")
def episodes(
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=200),
):
    statement = select(MemoryEpisode)
    if employee_id is not None:
        statement = statement.where(MemoryEpisode.primary_employee_id == employee_id)
    if project_id is not None:
        statement = statement.where(MemoryEpisode.project_id == project_id)
    return list(db.scalars(statement.order_by(MemoryEpisode.started_at.desc()).limit(limit)))


@router.get("/relations")
def relations(
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    status_filter: Optional[MemoryFactStatus] = Query(default=None, alias="status"),
):
    statement = select(MemoryRelation)
    if employee_id is not None:
        statement = statement.where(
            or_(
                MemoryRelation.source_entity_id == employee_id,
                MemoryRelation.target_entity_id == employee_id,
            )
        )
    if status_filter is not None:
        statement = statement.where(MemoryRelation.status == status_filter)
    return list(db.scalars(statement.order_by(MemoryRelation.importance.desc()).limit(100)))


@router.get("/search", response_model=MemorySearchRead)
def search(
    q: str,
    db: Session = Depends(get_db),
    employee_id: Optional[uuid.UUID] = None,
    include_history: bool = False,
):
    query = func.websearch_to_tsquery("simple", q.strip())
    fact_text = func.to_tsvector(
        "simple", func.concat_ws(" ", MemoryFact.subject_text, MemoryFact.object_text)
    )
    episode_text = func.to_tsvector(
        "simple", func.concat_ws(" ", MemoryEpisode.title, MemoryEpisode.summary)
    )
    fact_statement = select(MemoryFact).where(fact_text.op("@@")(query))
    if not include_history:
        fact_statement = fact_statement.where(MemoryFact.status == MemoryFactStatus.CURRENT)
    if employee_id is not None:
        fact_statement = fact_statement.where(
            or_(MemoryFact.subject_id == employee_id, MemoryFact.object_id == employee_id)
        )
    episode_statement = select(MemoryEpisode).where(episode_text.op("@@")(query))
    if employee_id is not None:
        episode_statement = episode_statement.where(
            MemoryEpisode.primary_employee_id == employee_id
        )
    return MemorySearchRead(
        facts=list(db.scalars(fact_statement.limit(20))),
        episodes=[
            {"id": str(item.id), "title": item.title, "summary": item.summary}
            for item in db.scalars(episode_statement.limit(20))
        ],
        relations=[],
    )


@router.get("/timeline/{entity_type}/{entity_id}", response_model=list[ActivityEventRead])
def timeline(entity_type: str, entity_id: uuid.UUID, db: Session = Depends(get_db)):
    """Append-only operational history for a blocker, task, commitment, etc."""
    return list(
        db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.entity_type == entity_type, ActivityEvent.entity_id == entity_id)
            .order_by(ActivityEvent.occurred_at.asc(), ActivityEvent.recorded_at.asc())
        )
    )


@router.get("/evidence/{memory_kind}/{memory_id}")
def evidence(memory_kind: str, memory_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return provenance links without widening raw-message access."""
    rows = db.execute(
        select(MemorySource, MemoryEvidenceLink)
        .join(MemoryEvidenceLink, MemoryEvidenceLink.memory_source_id == MemorySource.id)
        .where(
            MemoryEvidenceLink.memory_kind == memory_kind, MemoryEvidenceLink.memory_id == memory_id
        )
    ).all()
    return [
        {
            "source_type": source.source_type,
            "source_id": str(source.source_id) if source.source_id else None,
            "conversation_id": str(source.conversation_id) if source.conversation_id else None,
            "message_id": str(source.message_id) if source.message_id else None,
            "activity_event_id": str(source.activity_event_id)
            if source.activity_event_id
            else None,
        }
        for source, _ in rows
    ]


@router.get("/context/{employee_id}", response_model=CompiledMemoryContext)
def context(employee_id: uuid.UUID, db: Session = Depends(get_db)):
    return MemoryService.compile_context(db, employee_id)


@router.post("/context/compile", response_model=CompiledMemoryContext)
def compile_context(employee_id: uuid.UUID, db: Session = Depends(get_db)):
    return MemoryService.compile_context(db, employee_id)


@router.post("/consolidate")
def consolidate(retry_failed: bool = False, db: Session = Depends(get_db)):
    """Internal/manual trigger for safely processing queued memory events."""
    return MemoryConsolidationService.run(db, retry_failed=retry_failed)


@router.post("/backfill")
def backfill(db: Session = Depends(get_db)):
    """Queue existing local evidence without sending any external message."""
    return MemoryBackfillService.enqueue_existing_evidence(db)


@router.get("/procedures", response_model=list[ManagementProcedureRead])
def procedures(db: Session = Depends(get_db)):
    return list(
        db.scalars(select(ManagementProcedure).order_by(ManagementProcedure.created_at.desc()))
    )


@router.post("/procedures/{procedure_id}/approve", response_model=ManagementProcedureRead)
def approve_procedure(
    procedure_id: uuid.UUID, payload: ProcedureDecision, db: Session = Depends(get_db)
):
    return MemoryService.approve_procedure(db, procedure_id, payload.approved_by)


@router.post("/procedures/{procedure_id}/reject", response_model=ManagementProcedureRead)
def reject_procedure(
    procedure_id: uuid.UUID, payload: ProcedureDecision, db: Session = Depends(get_db)
):
    return MemoryService.reject_procedure(db, procedure_id, payload.approved_by)
