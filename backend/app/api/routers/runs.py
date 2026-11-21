import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.enums import ApprovalStatus, RunStatus
from app.db.models import Agent, BugDraft, Run, RunEvent, Task, TestCase
from app.db.session import SessionLocal
from app.runtime.registry import available_runtimes
from app.schemas.run import (
    ApprovalDecision,
    ApprovalDecisionResult,
    ApprovalRead,
    ArtifactRead,
    BugRead,
    RunEventRead,
    RunRead,
    RunStart,
    RuntimeStatus,
    SubAgentRead,
    TestCaseRead,
    UsageRow,
)
from app.services import runs as service
from app.worker.heartbeat import workers_online

router = APIRouter(tags=["runs"])


async def _read(session: AsyncSession, run: Run) -> RunRead:
    task = await session.get(Task, run.task_id)
    agent = await session.get(Agent, run.agent_id)
    resumed_by = await session.scalar(select(Run.id).where(Run.resumes_run_id == run.id).limit(1))
    totals = {}
    if run.kind == "orchestrator":
        cost, toks = (
            await session.execute(
                select(
                    func.coalesce(func.sum(Run.cost_usd), 0),
                    func.coalesce(func.sum(Run.input_tokens + Run.output_tokens), 0),
                ).where(Run.parent_run_id == run.id)
            )
        ).one()
        totals = {
            "total_cost_usd": run.cost_usd + cost,
            "total_tokens": run.input_tokens + run.output_tokens + int(toks),
        }
    return RunRead.model_validate(run).model_copy(
        update={
            "task_title": task.title if task else None,
            "agent_name": agent.name if agent else None,
            "resumed_by_run_id": resumed_by,
            **totals,
        }
    )


@router.get("/runtime/status", response_model=RuntimeStatus)
async def runtime_status(session: SessionDep, user: CurrentUser):
    s = get_settings()
    return RuntimeStatus(
        workers_online=await workers_online(session),
        azure_configured=s.azure_configured,
        deployment=s.azure_openai_deployment,
        runtimes=available_runtimes(),
    )


@router.post("/tasks/{task_id}/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def start_run(task_id: uuid.UUID, session: SessionDep, user: CurrentUser, body: RunStart | None = None):
    """Run the task. Optional body: test only some pages, or split the pages over parallel sub-agents."""
    run = await service.start_run(session, user.org_id, task_id, user.id, options=body)
    return await _read(session, run)


@router.get("/runs", response_model=list[RunRead])
async def list_runs(
    session: SessionDep,
    user: CurrentUser,
    task_id: uuid.UUID | None = None,
    status_: RunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    top_level: bool = Query(default=False, description="Hide the sub-agent runs of parallel runs"),
    since: datetime | None = Query(default=None, description="Created at or after (ISO date-time)"),
    until: datetime | None = Query(default=None, description="Created before (ISO date-time)"),
):
    runs = await service.list_runs(
        session,
        user.org_id,
        task_id=task_id,
        status=status_,
        limit=limit,
        top_level=top_level,
        since=since,
        until=until,
    )
    return [await _read(session, r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await _read(session, await service.get_run(session, user.org_id, run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await _read(session, await service.cancel_run(session, user.org_id, run_id))


@router.get("/runs/{run_id}/events", response_model=list[RunEventRead])
async def list_events(run_id: uuid.UUID, session: SessionDep, user: CurrentUser, after_seq: int = 0):
    await service.get_run(session, user.org_id, run_id)
    return await service.run_events(session, run_id, after_seq)


@router.get("/runs/{run_id}/stream")
async def stream_events(
    run_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUser, after_seq: int = 0
):
    """Server-Sent Events: new run events plus run status, until the run ends."""
    await service.get_run(session, user.org_id, run_id)

    async def gen():
        seq = after_seq
        last_run = None
        idle = 0
        while not await request.is_disconnected():
            async with SessionLocal() as s:
                events = await service.run_events(s, run_id, seq)
                run = await s.get(Run, run_id)
                run_payload = (await _read(s, run)).model_dump(mode="json")
            for e in events:
                seq = e.seq
                data = RunEventRead.model_validate(e).model_dump(mode="json")
                yield f"event: run_event\nid: {e.seq}\ndata: {json.dumps(data)}\n\n"
            if run_payload != last_run:
                last_run = run_payload
                yield f"event: run\ndata: {json.dumps(run_payload)}\n\n"
            if run.status not in (RunStatus.queued, RunStatus.running, RunStatus.waiting_children) and not events:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0 if events else idle + 1
            if idle and idle % 20 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


def _activity(event: RunEvent | None) -> str | None:
    """One line saying what a sub-agent is doing, from its latest live-log event."""
    if event is None:
        return None
    p = event.payload or {}
    if event.type == "tool_call":
        args = p.get("arguments") or {}
        detail = args.get("url") or args.get("element") or args.get("text") or args.get("case") or args.get("title")
        return f"{p.get('tool')}: {str(detail)[:80]}" if detail else str(p.get("tool"))
    if event.type == "message":
        return str(p.get("text", ""))[:120]
    if event.type == "status":
        return f"status: {p.get('status')}"
    return event.type


@router.get("/runs/{run_id}/subagents", response_model=list[SubAgentRead])
async def subagents(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    """Live lanes of a parallel run: one per sub-agent, with status, progress and current activity."""
    parent = await service.get_run(session, user.org_id, run_id)
    children = await service.child_runs(session, parent.id)
    lanes: dict[uuid.UUID, list[Run]] = {}
    for c in children:
        lanes.setdefault(c.task_id, []).append(c)
    out = []
    for runs in lanes.values():
        first, last = runs[0], runs[-1]
        ids = [r.id for r in runs]
        statuses = list(await session.scalars(select(TestCase.status).where(TestCase.run_id.in_(ids))))
        n_bugs = await session.scalar(select(func.count()).select_from(BugDraft).where(BugDraft.run_id.in_(ids)))
        latest = await session.scalar(
            select(RunEvent)
            .where(RunEvent.run_id == last.id, RunEvent.type.in_(["tool_call", "message", "status"]))
            .order_by(RunEvent.seq.desc())
            .limit(1)
        )
        usage = await session.scalar(
            select(RunEvent)
            .where(RunEvent.run_id == last.id, RunEvent.type == "usage")
            .order_by(RunEvent.seq.desc())
            .limit(1)
        )
        u = usage.payload if usage else {}
        done_cost = float(sum(r.cost_usd for r in runs[:-1]))
        live_cost = float(u.get("cost_usd", 0)) if last.status == RunStatus.running else float(last.cost_usd)
        opts = first.options or {}
        out.append(
            SubAgentRead(
                index=int(opts.get("index", 0)),
                label=str(opts.get("label", "")),
                pages=list(opts.get("pages") or []),
                task_id=first.task_id,
                run_id=last.id,
                status=last.status,
                started_at=first.started_at,
                ended_at=last.ended_at,
                error=last.error,
                summary=last.summary,
                turn=u.get("turn"),
                max_turns=u.get("max_turns") or opts.get("max_turns"),
                cost_usd=round(done_cost + live_cost, 4),
                budget_usd=opts.get("budget_usd"),
                tokens=sum(r.input_tokens + r.output_tokens for r in runs)
                or int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0)),
                activity=_activity(latest),
                activity_at=latest.created_at if latest else None,
                cases_total=len(statuses),
                cases_pass=statuses.count("pass"),
                cases_fail=statuses.count("fail"),
                cases_blocked=statuses.count("blocked"),
                bugs=n_bugs or 0,
            )
        )
    return sorted(out, key=lambda lane: lane.index)


@router.get("/runs/{run_id}/test-cases", response_model=list[TestCaseRead])
async def test_cases(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.run_test_cases(session, await service.get_run(session, user.org_id, run_id))


@router.get("/runs/{run_id}/bugs", response_model=list[BugRead])
async def bugs(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.run_bugs(session, await service.get_run(session, user.org_id, run_id))


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactRead])
async def artifacts(run_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.run_artifacts(session, await service.get_run(session, user.org_id, run_id))


@router.get("/artifacts/{artifact_id}/file")
async def artifact_file(artifact_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    art = await service.get_artifact(session, user.org_id, artifact_id)
    path = Path(art.path).resolve()
    root = get_settings().artifacts_dir.resolve()
    if root not in path.parents or not path.is_file():
        raise NotFound("Artifact file is missing")
    return FileResponse(path, media_type=art.mime)


@router.get("/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    session: SessionDep,
    user: CurrentUser,
    status_: ApprovalStatus | None = Query(default=None, alias="status"),
    since: datetime | None = None,
    until: datetime | None = None,
):
    out = []
    for ap in await service.list_approvals(session, user.org_id, status_, since, until):
        run = await session.get(Run, ap.run_id)
        task = await session.get(Task, run.task_id)
        out.append(ApprovalRead.model_validate(ap).model_copy(update={"task_id": task.id, "task_title": task.title}))
    return out


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalDecisionResult)
async def decide(approval_id: uuid.UUID, body: ApprovalDecision, session: SessionDep, user: CurrentUser):
    ap, resume = await service.decide(
        session,
        user.org_id,
        approval_id,
        user.id,
        body.decision == "approve",
        body.comment,
        body.payload,
        body.operation_key,
    )
    return ApprovalDecisionResult(approval=ApprovalRead.model_validate(ap), resume_run_id=resume.id if resume else None)


@router.get("/usage", response_model=list[UsageRow])
async def usage(session: SessionDep, user: CurrentUser):
    return await service.usage_summary(session, user.org_id)
