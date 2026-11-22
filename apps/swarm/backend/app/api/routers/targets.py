import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.common import Message
from app.schemas.target import TargetCreate, TargetRead, TargetUpdate
from app.services import targets as service

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=list[TargetRead])
async def list_targets(session: SessionDep, user: CurrentUser):
    return await service.list_targets(session, user.org_id)


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
async def create_target(body: TargetCreate, session: SessionDep, user: CurrentUser):
    return await service.create_target(session, user.org_id, body)


@router.get("/{target_id}", response_model=TargetRead)
async def get_target(target_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.get_target(session, user.org_id, target_id)


@router.patch("/{target_id}", response_model=TargetRead)
async def update_target(target_id: uuid.UUID, body: TargetUpdate, session: SessionDep, user: CurrentUser):
    return await service.update_target(session, user.org_id, target_id, body)


@router.delete("/{target_id}", response_model=Message)
async def delete_target(target_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await service.delete_target(session, user.org_id, target_id)
    return Message()
