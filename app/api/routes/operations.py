"""Prism-owned views of the separate computer execution service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.routes.prism_v22 import require_v22
from app.api.routes.work import require_v24
from app.schemas.workspace import (
    WorkspacePosition,
    WorkspaceSecret,
    WorkspaceTarget,
    WorkspaceTask,
)
from app.services.qa_swarm_client import QaSwarmClient, SwarmError

router = APIRouter(
    prefix="/api/v2/operations",
    tags=["Prism operations"],
    dependencies=[Depends(require_v22), Depends(require_v24)],
)


def _unavailable(exc: SwarmError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/overview")
def overview() -> dict:
    """One request lets the Operations home load without repeated engine logins."""
    try:
        with QaSwarmClient() as client:
            return {
                "status": client.workspace_data("status"),
                "tasks": client.workspace_data("tasks"),
                "runs": client.workspace_data("runs"),
                "approvals": client.workspace_data("approvals"),
                "bugs": client.workspace_data("bugs"),
                "analytics": client.workspace_data("analytics"),
                "agents": client.workspace_data("agents"),
                "targets": client.workspace_data("targets"),
                "positions": client.workspace_data("positions"),
            }
    except SwarmError as exc:
        raise _unavailable(exc) from exc


@router.get("/runs/{run_id}")
def run_detail(run_id: uuid.UUID) -> dict:
    try:
        with QaSwarmClient() as client:
            detail = client.workspace_run_detail(str(run_id))
    except SwarmError as exc:
        raise _unavailable(exc) from exc
    detail["run"].pop("result", None)
    # Tool arguments and results can contain sign-in values or private messages.
    # The manager sees event type and progress here; the live computer stays in its existing panel.
    detail["events"] = [
        {
            "seq": event.get("seq"),
            "type": event.get("type"),
            "created_at": event.get("created_at"),
            "tool": (event.get("payload") or {}).get("tool")
            if event.get("type") == "tool_call"
            else None,
            "status": (event.get("payload") or {}).get("status")
            if event.get("type") == "status"
            else None,
        }
        for event in detail["events"]
    ]
    return detail


@router.get("/artifacts/{artifact_id}/file")
def artifact_file(artifact_id: uuid.UUID) -> Response:
    try:
        with QaSwarmClient() as client:
            data, _content_type = client.artifact_file(str(artifact_id))
    except SwarmError as exc:
        raise _unavailable(exc) from exc
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="prism-artifact-{artifact_id}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/analytics")
def analytics(
    days: int = Query(default=30, ge=1, le=365), agent_id: uuid.UUID | None = None
) -> dict:
    try:
        with QaSwarmClient() as client:
            return client.workspace_data(
                "analytics", days=days, agent_id=str(agent_id) if agent_id else None
            )
    except SwarmError as exc:
        raise _unavailable(exc) from exc


def _save(section: str, data: dict, record_id: uuid.UUID | None = None) -> dict:
    try:
        with QaSwarmClient() as client:
            return client.workspace_save(section, data, str(record_id) if record_id else None)
    except SwarmError as exc:
        raise _unavailable(exc) from exc


@router.post("/tasks", status_code=201)
def create_task(body: WorkspaceTask) -> dict:
    return _save("tasks", body.model_dump(mode="json"))


@router.patch("/tasks/{record_id}")
def update_task(record_id: uuid.UUID, body: WorkspaceTask) -> dict:
    return _save("tasks", body.model_dump(mode="json"), record_id)


@router.post("/positions", status_code=201)
def create_position(body: WorkspacePosition) -> dict:
    return _save("positions", body.model_dump(mode="json"))


@router.patch("/positions/{record_id}")
def update_position(record_id: uuid.UUID, body: WorkspacePosition) -> dict:
    return _save("positions", body.model_dump(mode="json"), record_id)


@router.post("/targets", status_code=201)
def create_target(body: WorkspaceTarget) -> dict:
    return _save("targets", body.model_dump(mode="json"))


@router.patch("/targets/{record_id}")
def update_target(record_id: uuid.UUID, body: WorkspaceTarget) -> dict:
    return _save("targets", body.model_dump(mode="json"), record_id)


@router.post("/secrets", status_code=201)
def create_secret(body: WorkspaceSecret) -> dict:
    return _save(
        "secrets",
        {"name": body.name, "scope": body.scope, "value": body.value.get_secret_value()},
    )


@router.delete("/{section}/{record_id}", status_code=204)
def delete_record(section: str, record_id: uuid.UUID) -> Response:
    if section not in {"positions", "targets", "secrets"}:
        raise HTTPException(status_code=404, detail="Unknown Workspace action")
    try:
        with QaSwarmClient() as client:
            client.workspace_delete(section, str(record_id))
    except SwarmError as exc:
        raise _unavailable(exc) from exc
    return Response(status_code=204)


@router.get("/{section}")
def section_data(section: str) -> list[dict] | dict:
    if section not in {
        "agents",
        "tasks",
        "runs",
        "approvals",
        "bugs",
        "positions",
        "targets",
        "secrets",
        "usage",
        "analytics",
        "status",
    }:
        raise HTTPException(status_code=404, detail="Unknown Operations section")
    try:
        with QaSwarmClient() as client:
            return client.workspace_data(section)
    except SwarmError as exc:
        raise _unavailable(exc) from exc
