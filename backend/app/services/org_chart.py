import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Agent, OrgPosition
from app.schemas.org_chart import PositionCreate, PositionUpdate
from app.services.common import apply_updates, get_owned


async def list_positions(session: AsyncSession, org_id: uuid.UUID) -> list[OrgPosition]:
    q = select(OrgPosition).where(OrgPosition.org_id == org_id).order_by(OrgPosition.sort_order, OrgPosition.created_at)
    return list(await session.scalars(q))


def _check_holder(changes: dict, current: OrgPosition | None = None) -> None:
    """Keep holder fields consistent: only agent seats link an agent; vacant seats have no name."""
    holder = changes.get("holder_type", current.holder_type if current else "vacant")
    if holder != "agent":
        changes["agent_id"] = None
    if holder == "vacant":
        changes["holder_name"] = ""


async def _check_refs(session: AsyncSession, org_id: uuid.UUID, changes: dict, position_id: uuid.UUID | None = None):
    if changes.get("agent_id"):
        await get_owned(session, Agent, changes["agent_id"], org_id)
    parent_id = changes.get("parent_id")
    if parent_id:
        await get_owned(session, OrgPosition, parent_id, org_id)
        # Refuse cycles: the new parent may not be this position or one of its descendants.
        seen = parent_id
        while seen is not None:
            if seen == position_id:
                raise AppError("A position cannot report to itself or to someone below it.", code="cycle")
            seen = await session.scalar(select(OrgPosition.parent_id).where(OrgPosition.id == seen))


async def create_position(session: AsyncSession, org_id: uuid.UUID, data: PositionCreate) -> OrgPosition:
    changes = data.model_dump()
    _check_holder(changes)
    await _check_refs(session, org_id, changes)
    pos = OrgPosition(org_id=org_id, **changes)
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    return pos


async def update_position(
    session: AsyncSession, org_id: uuid.UUID, position_id: uuid.UUID, data: PositionUpdate
) -> OrgPosition:
    pos = await get_owned(session, OrgPosition, position_id, org_id)
    changes = data.model_dump(exclude_unset=True)
    _check_holder(changes, pos)
    await _check_refs(session, org_id, changes, position_id=pos.id)
    apply_updates(pos, changes)
    await session.commit()
    await session.refresh(pos)
    return pos


async def delete_position(session: AsyncSession, org_id: uuid.UUID, position_id: uuid.UUID) -> None:
    """Delete a position; its direct reports move up to its parent."""
    pos = await get_owned(session, OrgPosition, position_id, org_id)
    await session.execute(update(OrgPosition).where(OrgPosition.parent_id == pos.id).values(parent_id=pos.parent_id))
    await session.delete(pos)
    await session.commit()
