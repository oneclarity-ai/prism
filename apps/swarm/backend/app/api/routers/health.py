from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.schemas.common import Message

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=Message)
async def health() -> Message:
    return Message()


@router.get("/db", response_model=Message)
async def health_db(session: SessionDep) -> Message:
    await session.execute(text("SELECT 1"))
    return Message()
