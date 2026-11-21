from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.routes.prism_v22 import require_v22
from app.core.config import get_settings
from app.db.session import get_db
from app.models.prism_v22 import Prism
from app.schemas.common import Schema
from app.schemas.prism_v22 import PrismProfileUpdate, PrismRead
from app.services import qa_run_service
from app.services.computer_service import ComputerService
from app.services.errors import NotFoundError
from app.services.prism_login_service import PrismLoginService
from app.services.prism_profile_service import PrismProfileService
from app.services.qa_run_service import QaRunService
from app.services.qa_swarm_client import SwarmError
from app.services.work_bridge_service import WorkBridgeService, verify


def require_v24() -> None:
    if not get_settings().prism_v24_enabled:
        raise HTTPException(status_code=404, detail="Prism v2.4 is not enabled")


router = APIRouter(
    tags=["Prism computers"], dependencies=[Depends(require_v22), Depends(require_v24)]
)


@router.patch("/api/v2/prisms/{prism_id}/profile", response_model=PrismRead)
def update_profile(
    prism_id: uuid.UUID, payload: PrismProfileUpdate, db: Session = Depends(get_db)
) -> Prism:
    """Capabilities, sign-in policy and "How I'll work". The Prism's agent follows on its next task."""

    return PrismProfileService.update(db, prism_id, payload)


@router.get("/api/v2/prisms/{prism_id}/computer")
def computer_state(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return ComputerService.state(db, prism_id)


@router.get("/api/v2/prisms/{prism_id}/computer/live")
def computer_live(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """Live screen of the Prism's computer. Held open for as long as someone is watching."""
    return StreamingResponse(
        ComputerService.live(db, prism_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/api/v2/prisms/{prism_id}/computer/stop")
def computer_stop(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return ComputerService.stop(db, prism_id)


@router.post("/api/v2/prisms/{prism_id}/computer/reset")
def computer_reset(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return ComputerService.reset(db, prism_id)


@router.get("/api/v2/prisms/{prism_id}/logins")
def list_logins(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    return PrismLoginService.list(db, prism_id)


@router.delete("/api/v2/prisms/{prism_id}/logins/{login_id}")
def remove_login(
    prism_id: uuid.UUID, login_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[dict]:
    prism = db.get(Prism, prism_id)
    if prism is None:
        raise NotFoundError("Prism was not found")
    try:
        with qa_run_service.make_client() as client:
            PrismLoginService.remove(db, prism, login_id, client)
    except SwarmError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return PrismLoginService.list(db, prism_id)


# ---------- the engine calling back (Teams tools). No operator token: signed instead. ----------

bridge = APIRouter(tags=["Prism computers (engine)"], dependencies=[Depends(require_v24)])


class BridgeBody(Schema):
    query: str | None = None
    person: str | None = None
    to: str | None = None
    body: str | None = None


@bridge.post("/api/v2/bridge/runs/{run_ref}/teams/{action}")
async def teams_bridge(
    run_ref: str, action: str, request: Request, db: Session = Depends(get_db)
) -> dict:
    raw = await request.body()
    if not verify(
        get_settings().work_bridge_secret,
        request.headers.get("X-Prism-Timestamp", ""),
        raw,
        request.headers.get("X-Prism-Signature", ""),
    ):
        raise HTTPException(status_code=401, detail="Not signed")
    data = BridgeBody.model_validate_json(raw or b"{}")
    if action == "read" and data.person:
        return WorkBridgeService.read(db, run_ref, data.person)
    if action == "search" and data.query:
        return WorkBridgeService.search(db, run_ref, data.query, data.person)
    if action == "draft" and data.to and data.body:
        return WorkBridgeService.draft(db, run_ref, data.to, data.body)
    raise HTTPException(status_code=400, detail="Missing details for that Teams action")


__all__ = ["router", "bridge", "QaRunService"]
