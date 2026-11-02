from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.prism_v22 import require_v22
from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.qa import QaRun
from app.schemas.qa import QaDecision, QaPlanCreate, QaPlanResult, QaStart, QaStatusRead
from app.services.brain_service import BrainService
from app.services.qa_run_service import QaRunService

router = APIRouter(tags=["QA tester"], dependencies=[Depends(require_v22)])


@router.get("/api/v2/qa/status", response_model=QaStatusRead)
def qa_status() -> QaStatusRead:
    available, reason = QaRunService.available()
    return QaStatusRead(
        available=available, reason=reason, computers=get_settings().prism_v24_enabled
    )


@router.post("/api/v2/prisms/{prism_id}/qa/plan", response_model=QaPlanResult)
def plan_test(
    prism_id: uuid.UUID,
    payload: QaPlanCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> QaPlanResult:
    """Turn a chat request into a test plan the manager approves. handled=false: not a test request."""

    background.add_task(BrainService.learn_in_background, prism_id, payload.content)
    result = QaRunService.handle_chat(db, thread_id=payload.thread_id, text=payload.content)
    return QaPlanResult(**result)


@router.get("/api/v2/prisms/{prism_id}/qa/runs")
def list_runs(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(
        select(QaRun)
        .where(QaRun.prism_id == prism_id, QaRun.state != "planned")
        .order_by(QaRun.created_at.desc())
        .limit(30)
    )
    return [QaRunService.snapshot(db, run) for run in runs]


@router.get("/api/v2/qa/runs/{qa_run_id}")
def get_run(qa_run_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return QaRunService.snapshot(db, QaRunService.get(db, qa_run_id))


@router.post("/api/v2/qa/runs/{qa_run_id}/start")
def start_run(qa_run_id: uuid.UUID, payload: QaStart, db: Session = Depends(get_db)) -> dict:
    run = QaRunService.start(db, qa_run_id, payload.model_dump(exclude_none=True))
    return QaRunService.snapshot(db, run)


@router.post("/api/v2/qa/runs/{qa_run_id}/cancel")
def cancel_run(qa_run_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return QaRunService.snapshot(db, QaRunService.cancel(db, qa_run_id))


@router.post("/api/v2/qa/approvals/{approval_id}/decision")
def decide(approval_id: uuid.UUID, payload: QaDecision, db: Session = Depends(get_db)) -> dict:
    login = None
    if payload.login is not None:
        login = {
            "username": payload.login.username,
            "password": payload.login.password.get_secret_value(),
            "remember": payload.login.remember,
        }
    approval = QaRunService.decide(
        db, approval_id, payload.decision, payload.comment, payload.answer, login
    )
    return QaRunService.snapshot(db, QaRunService.get(db, approval.qa_run_id))


@router.get("/api/v2/qa/runs/{qa_run_id}/screens/{index}")
def screenshot(qa_run_id: uuid.UUID, index: int, db: Session = Depends(get_db)) -> Response:
    data, content_type = QaRunService.artifact(db, qa_run_id, index)
    return Response(
        content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/api/v2/qa/runs/{qa_run_id}/frame")
def latest_frame(qa_run_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """The newest live view of the Prism's screen. Fetched again whenever the run's frame count changes."""

    data, content_type = QaRunService.latest_frame(db, qa_run_id)
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.get("/api/v2/qa/runs/{qa_run_id}/files/{index}")
def download_file(qa_run_id: uuid.UUID, index: int, db: Session = Depends(get_db)) -> Response:
    data, content_type, name = QaRunService.file(db, qa_run_id, index)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ") or "file"
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


def _read_snapshot(qa_run_id: uuid.UUID) -> dict | None:
    with SessionLocal() as db:
        run = db.get(QaRun, qa_run_id)
        return QaRunService.snapshot(db, run) if run is not None else None


@router.get("/api/v2/qa/runs/{qa_run_id}/stream")
async def stream(qa_run_id: uuid.UUID, request: Request) -> StreamingResponse:
    """Live view of one run: the screen, current page, action and progress, until it ends."""

    first = await asyncio.to_thread(_read_snapshot, qa_run_id)
    if first is None:
        from app.services.errors import NotFoundError

        raise NotFoundError("That test run was not found")

    async def events():
        last = ""
        idle = 0
        while not await request.is_disconnected():
            snap = await asyncio.to_thread(_read_snapshot, qa_run_id)
            if snap is None:
                return
            body = json.dumps(snap, default=str)
            digest = hashlib.sha1(body.encode()).hexdigest()
            if digest != last:
                last = digest
                idle = 0
                yield f"event: state\ndata: {body}\n\n"
            else:
                idle += 1
                if idle % 15 == 0:
                    yield ": keep-alive\n\n"
            if not snap["active"]:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
