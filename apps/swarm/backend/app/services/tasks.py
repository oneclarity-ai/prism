import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TaskStatus
from app.db.models import Agent, TargetApp, Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.common import apply_updates, get_owned


async def list_tasks(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    status: TaskStatus | None = None,
    agent_id: uuid.UUID | None = None,
    target_app_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Task]:
    query = select(Task).where(Task.org_id == org_id)
    if status:
        query = query.where(Task.status == status)
    if agent_id:
        query = query.where(Task.agent_id == agent_id)
    if target_app_id:
        query = query.where(Task.target_app_id == target_app_id)
    rows = await session.scalars(query.order_by(Task.created_at.desc()).limit(limit).offset(offset))
    return list(rows)


async def get_task(session: AsyncSession, org_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    return await get_owned(session, Task, task_id, org_id)


async def _check_refs(session: AsyncSession, org_id: uuid.UUID, changes: dict) -> None:
    if changes.get("agent_id"):
        await get_owned(session, Agent, changes["agent_id"], org_id)
    if changes.get("target_app_id"):
        await get_owned(session, TargetApp, changes["target_app_id"], org_id)
    if changes.get("parent_id"):
        await get_owned(session, Task, changes["parent_id"], org_id)


async def create_task(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, data: TaskCreate) -> Task:
    if data.operation_key:
        existing = await session.scalar(
            select(Task).where(Task.org_id == org_id, Task.operation_key == data.operation_key)
        )
        if existing is not None:
            return existing
    changes = data.model_dump()
    await _check_refs(session, org_id, changes)
    changes["scope"] = data.scope.model_dump()
    task = Task(org_id=org_id, created_by_id=user_id, **changes)
    session.add(task)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if not data.operation_key:
            raise
        existing = await session.scalar(
            select(Task).where(Task.org_id == org_id, Task.operation_key == data.operation_key)
        )
        if existing is None:
            raise
        return existing
    await session.refresh(task)
    return task


async def update_task(session: AsyncSession, org_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate) -> Task:
    task = await get_task(session, org_id, task_id)
    changes = data.model_dump(exclude_unset=True)
    await _check_refs(session, org_id, changes)
    if "scope" in changes and data.scope is not None:
        changes["scope"] = data.scope.model_dump()
    apply_updates(task, changes)
    await session.commit()
    await session.refresh(task)
    return task
