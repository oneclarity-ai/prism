from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.intelligence import ManagementDecision, ManagementRisk, ManagerFeedback
from app.schemas.intelligence import (
    AttentionItem,
    ChangeRead,
    DailyBrief,
    DecisionRead,
    DependencyEdgeCreate,
    DependencyEdgeRead,
    DependencyGraphRead,
    EmployeeManagementState,
    IntelligenceCycleResult,
    ManagementQueryAnswer,
    ManagementQueryRequest,
    ManagerFeedbackCreate,
    ManagerFeedbackRead,
    RiskRead,
)
from app.services.attention_queue_service import AttentionQueueService
from app.services.change_intelligence_service import ChangeIntelligenceService
from app.services.daily_brief_service import DailyBriefService
from app.services.dependency_graph_service import DependencyGraphService
from app.services.management_intelligence_service import ManagementIntelligenceService
from app.services.management_query_service import ManagementQueryService
from app.services.management_state_service import ManagementStateService
from app.services.manager_feedback_service import ManagerFeedbackService
from app.services.risk_intelligence_service import RiskIntelligenceService
from app.services.temporal_memory_service import TemporalMemoryService

router = APIRouter(prefix="/api/v2/management", tags=["management intelligence"])


@router.get("/state", response_model=list[EmployeeManagementState])
def managed_state(db: Session = Depends(get_db)):
    return ManagementStateService.all_managed(db)


@router.get("/state/{employee_id}", response_model=EmployeeManagementState)
def employee_state(employee_id: uuid.UUID, db: Session = Depends(get_db)):
    return ManagementStateService.employee_state(db, employee_id)


@router.get("/memory/context/{employee_id}")
def temporal_context(
    employee_id: uuid.UUID,
    include_history: bool = False,
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return TemporalMemoryService.retrieve(
        db, employee_id=employee_id, include_history=include_history, limit=limit
    )


@router.get("/dependencies", response_model=DependencyGraphRead)
def dependency_graph(include_resolved: bool = False, db: Session = Depends(get_db)):
    return DependencyGraphService.graph(db, include_resolved=include_resolved)


@router.post(
    "/dependencies", response_model=DependencyEdgeRead, status_code=status.HTTP_201_CREATED
)
def create_dependency(payload: DependencyEdgeCreate, db: Session = Depends(get_db)):
    edge = DependencyGraphService.create(db, payload)
    return DependencyEdgeRead(
        id=edge.id,
        source_entity_type=edge.source_entity_type,
        source_entity_id=edge.source_entity_id,
        target_entity_type=edge.target_entity_type,
        target_entity_id=edge.target_entity_id,
        relation_type=edge.relation_type,
        status=edge.status,
        blocker_id=edge.blocker_id,
        task_id=edge.task_id,
        project_id=edge.project_id,
        valid_from=edge.valid_from,
        valid_until=edge.valid_until,
        confidence=edge.confidence,
        reopened_from_id=edge.reopened_from_id,
        evidence=([f"message:{edge.source_message_id}"] if edge.source_message_id else []),
    )


@router.post("/dependencies/{edge_id}/resolve", response_model=DependencyEdgeRead)
def resolve_dependency(edge_id: uuid.UUID, db: Session = Depends(get_db)):
    edge = DependencyGraphService.resolve(db, edge_id)
    return next(
        item
        for item in DependencyGraphService.edges(db, include_resolved=True)
        if item.id == edge.id
    )


@router.post("/dependencies/{edge_id}/reopen", response_model=DependencyEdgeRead)
def reopen_dependency(edge_id: uuid.UUID, db: Session = Depends(get_db)):
    edge = DependencyGraphService.reopen(db, edge_id)
    return next(
        item
        for item in DependencyGraphService.edges(db, include_resolved=True)
        if item.id == edge.id
    )


@router.get("/dependencies/{entity_type}/{entity_id}/impact")
def dependency_impact(entity_type: str, entity_id: uuid.UUID, db: Session = Depends(get_db)):
    return DependencyGraphService.affected_by(db, entity_type, entity_id)


@router.post("/intelligence/run", response_model=IntelligenceCycleResult)
def run_intelligence(db: Session = Depends(get_db)):
    return ManagementIntelligenceService.run(db)


@router.post("/risks/refresh", response_model=list[RiskRead])
def refresh_risks(db: Session = Depends(get_db)):
    return RiskIntelligenceService.evaluate(db)


@router.get("/risks", response_model=list[RiskRead])
def risks(status_filter: str = Query("active", alias="status"), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(ManagementRisk)
            .where(ManagementRisk.status == status_filter)
            .order_by(ManagementRisk.last_evaluated_at.desc())
        )
    )


@router.get("/decisions", response_model=list[DecisionRead])
def decisions(
    action: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(ManagementDecision)
    if action:
        query = query.where(ManagementDecision.action == action)
    if status_filter:
        query = query.where(ManagementDecision.status == status_filter)
    return list(db.scalars(query.order_by(ManagementDecision.decided_at.desc()).limit(limit)))


@router.get("/attention", response_model=list[AttentionItem])
def attention(db: Session = Depends(get_db)):
    return AttentionQueueService.list(db)


@router.get("/brief/daily", response_model=DailyBrief)
def daily_brief(db: Session = Depends(get_db)):
    return DailyBriefService.build(db)


@router.get("/changes", response_model=list[ChangeRead])
def changes(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    employee_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return ChangeIntelligenceService.changes(
        db,
        since=since,
        until=until,
        employee_id=employee_id,
        project_id=project_id,
        entity_type=entity_type,
        limit=limit,
    )


@router.post("/query", response_model=ManagementQueryAnswer)
def management_query(payload: ManagementQueryRequest, db: Session = Depends(get_db)):
    return ManagementQueryService.answer(db, payload.question)


@router.post("/feedback", response_model=ManagerFeedbackRead, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: ManagerFeedbackCreate, db: Session = Depends(get_db)):
    return ManagerFeedbackService.create(db, payload)


@router.get("/feedback", response_model=list[ManagerFeedbackRead])
def feedback(
    active_only: bool = True,
    employee_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
):
    query = select(ManagerFeedback)
    if active_only:
        query = query.where(ManagerFeedback.is_active.is_(True))
    if employee_id:
        query = query.where(ManagerFeedback.employee_id == employee_id)
    if project_id:
        query = query.where(ManagerFeedback.project_id == project_id)
    return list(db.scalars(query.order_by(ManagerFeedback.created_at.desc())))


@router.delete("/feedback/{feedback_id}", response_model=ManagerFeedbackRead)
def deactivate_feedback(feedback_id: uuid.UUID, db: Session = Depends(get_db)):
    return ManagerFeedbackService.deactivate(db, feedback_id)
