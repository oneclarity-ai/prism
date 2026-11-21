import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.db.enums import TaskStatus
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import tasks as service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    session: SessionDep,
    user: CurrentUser,
    status_: TaskStatus | None = Query(default=None, alias="status"),
    agent_id: uuid.UUID | None = None,
    target_app_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return await service.list_tasks(
        session, user.org_id, status=status_, agent_id=agent_id, target_app_id=target_app_id, limit=limit, offset=offset
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, session: SessionDep, user: CurrentUser):
    return await service.create_task(session, user.org_id, user.id, body)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.get_task(session, user.org_id, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: uuid.UUID, body: TaskUpdate, session: SessionDep, user: CurrentUser):
    return await service.update_task(session, user.org_id, task_id, body)
