import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.core.security import decrypt_secret, encrypt_secret
from app.db.models import Secret
from app.services.common import get_owned


async def list_secrets(session: AsyncSession, org_id: uuid.UUID, scope: str | None = None) -> list[Secret]:
    query = select(Secret).where(Secret.org_id == org_id)
    if scope:
        query = query.where(Secret.scope == scope)
    rows = await session.scalars(query.order_by(Secret.name))
    return list(rows)


async def create_secret(
    session: AsyncSession, org_id: uuid.UUID, name: str, value: str, scope: str = "general", *, commit: bool = True
) -> Secret:
    exists = await session.scalar(select(Secret.id).where(Secret.org_id == org_id, Secret.name == name))
    if exists:
        raise Conflict(f"Secret '{name}' already exists")
    secret = Secret(org_id=org_id, name=name, scope=scope, encrypted_value=encrypt_secret(value))
    session.add(secret)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return secret


async def delete_secret(session: AsyncSession, org_id: uuid.UUID, secret_id: uuid.UUID) -> None:
    secret = await get_owned(session, Secret, secret_id, org_id)
    await session.delete(secret)
    await session.commit()


async def read_secret_value(session: AsyncSession, org_id: uuid.UUID, secret_id: uuid.UUID) -> str:
    """Internal only (runtime tools). Never expose through the API."""
    secret = await get_owned(session, Secret, secret_id, org_id)
    return decrypt_secret(secret.encrypted_value)
