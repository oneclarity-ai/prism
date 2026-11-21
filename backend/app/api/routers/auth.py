from fastapi import APIRouter, Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.security import create_session_token, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, UserRead
from app.schemas.common import Message

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
async def login(body: LoginRequest, response: Response, session: SessionDep) -> User:
    user = await session.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Wrong email or password")
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        create_session_token(user.id),
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return user


@router.post("/logout", response_model=Message)
async def logout(response: Response) -> Message:
    response.delete_cookie(get_settings().session_cookie_name)
    return Message()


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> User:
    return user
