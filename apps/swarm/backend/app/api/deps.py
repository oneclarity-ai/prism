from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.security import decode_session_token
from app.db.models import User
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _token_from_request(request: Request) -> str | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = _token_from_request(request)
    if not token:
        raise Unauthorized("Not signed in")
    user = await session.get(User, decode_session_token(token))
    if user is None or not user.is_active:
        raise Unauthorized("Not signed in")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
