import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound


async def get_owned[T](session: AsyncSession, model: type[T], obj_id: uuid.UUID, org_id: uuid.UUID) -> T:
    """Load a row by id and make sure it belongs to the caller's organization."""
    obj = await session.get(model, obj_id)
    if obj is None or getattr(obj, "org_id", None) != org_id:
        raise NotFound(f"{model.__name__} not found")
    return obj


def apply_updates(obj, data: dict) -> None:
    for field, value in data.items():
        setattr(obj, field, value)
