import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Secret, TargetApp
from app.schemas.target import TargetCreate, TargetUpdate, TestLogin
from app.services.common import apply_updates, get_owned
from app.services.secrets import create_secret


async def list_targets(session: AsyncSession, org_id: uuid.UUID) -> list[TargetApp]:
    rows = await session.scalars(select(TargetApp).where(TargetApp.org_id == org_id).order_by(TargetApp.name))
    return list(rows)


async def get_target(session: AsyncSession, org_id: uuid.UUID, target_id: uuid.UUID) -> TargetApp:
    return await get_owned(session, TargetApp, target_id, org_id)


async def _store_login(session: AsyncSession, target: TargetApp, login: TestLogin) -> None:
    await _drop_login(session, target)
    secret = await create_secret(
        session,
        target.org_id,
        name=f"target:{target.id}:test_login",
        value=json.dumps(login.model_dump()),
        scope="target_login",
        commit=False,
    )
    target.auth_secret_id = secret.id


async def _drop_login(session: AsyncSession, target: TargetApp) -> None:
    if target.auth_secret_id:
        secret = await session.get(Secret, target.auth_secret_id)
        target.auth_secret_id = None
        if secret:
            await session.delete(secret)
        await session.flush()


async def create_target(session: AsyncSession, org_id: uuid.UUID, data: TargetCreate) -> TargetApp:
    target = TargetApp(
        id=uuid.uuid4(),
        org_id=org_id,
        name=data.name,
        base_url=str(data.base_url),
        environment=data.environment,
        repo_url=str(data.repo_url) if data.repo_url else None,
        notes=data.notes,
        extra_origins=data.extra_origins,
    )
    session.add(target)
    await session.flush()
    if data.test_login:
        await _store_login(session, target, data.test_login)
    await session.commit()
    await session.refresh(target)
    return target


async def update_target(
    session: AsyncSession, org_id: uuid.UUID, target_id: uuid.UUID, data: TargetUpdate
) -> TargetApp:
    target = await get_target(session, org_id, target_id)
    changes = data.model_dump(exclude_unset=True, exclude={"test_login", "clear_test_login"})
    for url_field in ("base_url", "repo_url"):
        if changes.get(url_field) is not None:
            changes[url_field] = str(changes[url_field])
    apply_updates(target, changes)
    if data.clear_test_login:
        await _drop_login(session, target)
    elif data.test_login:
        await _store_login(session, target, data.test_login)
    await session.commit()
    await session.refresh(target)
    return target


async def delete_target(session: AsyncSession, org_id: uuid.UUID, target_id: uuid.UUID) -> None:
    target = await get_target(session, org_id, target_id)
    await _drop_login(session, target)
    await session.delete(target)
    await session.commit()
