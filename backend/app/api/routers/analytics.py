import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.db.models import BugDraft, Run, TargetApp, Task
from app.schemas.analytics import AnalyticsRead, BugListItem
from app.services.analytics import analytics

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsRead)
async def get_analytics(
    session: SessionDep,
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=365),
    agent_id: uuid.UUID | None = None,
    since: datetime | None = Query(default=None, description="Start (ISO date-time); overrides days"),
    until: datetime | None = Query(default=None, description="End, exclusive (ISO date-time)"),
):
    return await analytics(session, user.org_id, days, agent_id, since=since, until=until)


@router.get("/bugs", response_model=list[BugListItem])
async def list_bugs(
    session: SessionDep,
    user: CurrentUser,
    severity: str | None = None,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    include_duplicates: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
):
    """Every bug the agents found, across all runs, newest first."""
    q = (
        select(BugDraft, Run, Task, TargetApp)
        .join(Run, Run.id == BugDraft.run_id)
        .join(Task, Task.id == Run.task_id)
        .outerjoin(TargetApp, TargetApp.id == Task.target_app_id)
        .where(Run.org_id == user.org_id)
    )
    if since:
        q = q.where(BugDraft.created_at >= since)
    if until:
        q = q.where(BugDraft.created_at < until)
    if not include_duplicates:  # parallel runs: a bug two sub-agents found is listed once
        q = q.where(BugDraft.duplicate_of_id.is_(None))
    if severity:
        q = q.where(BugDraft.severity == severity)
    if status:
        q = q.where(BugDraft.status == status)
    rows = await session.execute(q.order_by(BugDraft.created_at.desc()).limit(limit))
    return [
        BugListItem(
            id=str(b.id),
            title=b.title,
            severity=b.severity,
            status=b.status,
            steps=b.steps,
            expected=b.expected,
            actual=b.actual,
            external_url=b.external_url,
            created_at=b.created_at.isoformat(),
            run_id=str(r.id),
            task_id=str(t.id),
            task_title=t.title,
            target_name=ta.name if ta else None,
            model=r.model,
        )
        for b, r, t, ta in rows
    ]
