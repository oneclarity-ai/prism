import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.common import Message
from app.schemas.target import SecretCreate, SecretRead
from app.services import secrets as service

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.get("", response_model=list[SecretRead])
async def list_secrets(session: SessionDep, user: CurrentUser, scope: str | None = None):
    return await service.list_secrets(session, user.org_id, scope)


@router.post("", response_model=SecretRead, status_code=status.HTTP_201_CREATED)
async def create_secret(body: SecretCreate, session: SessionDep, user: CurrentUser):
    return await service.create_secret(session, user.org_id, body.name, body.value, body.scope)


@router.delete("/{secret_id}", response_model=Message)
async def delete_secret(secret_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await service.delete_secret(session, user.org_id, secret_id)
    return Message()
