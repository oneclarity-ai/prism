import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.computers.manager import ComputerError, manager
from app.core.errors import AppError
from app.schemas.common import Message

router = APIRouter(prefix="/computers", tags=["computers"])


def _check(key: str) -> str:
    try:
        return manager.check_key(key)
    except ComputerError as exc:
        raise AppError("Unknown computer", code="not_found") from exc


@router.get("/{key}")
async def state(key: str, user: CurrentUser) -> dict:
    """missing | stopped | running. Docker problems read as 'unavailable'."""
    try:
        info = await manager.info(_check(key))
    except ComputerError:
        return {"key": key, "state": "unavailable"}
    return {"key": key, "state": info.state}


@router.get("/{key}/stream")
async def stream(key: str, user: CurrentUser) -> StreamingResponse:
    """Live view of the computer's screen as multipart JPEG. Only while the computer is running."""
    key = _check(key)
    try:
        info = await manager.info(key)
    except ComputerError as exc:
        raise AppError("The computer is not available", code="not_found") from exc
    if info.state != "running" or not info.stream_url:
        raise AppError("The computer is asleep", code="not_found")
    url = info.stream_url

    async def frames():
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5)) as client:
            try:
                async with client.stream("GET", url) as response:
                    async for chunk in response.aiter_raw():
                        yield chunk
            except httpx.HTTPError:
                return  # the computer stopped; the viewer sees the stream end

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/{key}/stop", response_model=Message)
async def stop(key: str, user: CurrentUser) -> Message:
    await manager.stop(_check(key))
    return Message()


@router.post("/{key}/reset", response_model=Message)
async def reset(key: str, user: CurrentUser) -> Message:
    """Clears the browser profile: every login and cookie of this computer is forgotten."""
    await manager.reset(_check(key))
    return Message()
