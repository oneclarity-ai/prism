import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import AppError, Conflict, NotFound
from app.core.logging import log
from app.db.enums import (
    AgentStatus,
    ApprovalStatus,
    BugStatus,
    RunKind,
    RunStatus,
    RunTrigger,
    TaskStatus,
)
from app.db.models import (
    Agent,
    Approval,
    Artifact,
    BudgetLedger,
    BugDraft,
    Run,
    RunEvent,
    Task,
    TestCase,
)
from app.runtime.registry import get_adapter
from app.schemas.run import RunStart
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.common import get_owned

ACTIVE = (
    RunStatus.queued,
    RunStatus.running,
    RunStatus.waiting_approval,
    RunStatus.waiting_children,
)
TERMINAL = (RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled, RunStatus.timed_out)


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


async def month_spend(session: AsyncSession, agent_id: uuid.UUID) -> Decimal:
    spent = await session.scalar(
        select(func.coalesce(func.sum(BudgetLedger.cost_usd), 0)).where(
            BudgetLedger.agent_id == agent_id, BudgetLedger.period == current_period()
        )
    )
    return Decimal(spent)


async def start_run(
    session: AsyncSession,
    org_id: uuid.UUID,
    task_id: uuid.UUID,
    user_id: uuid.UUID | None,
    trigger: RunTrigger = RunTrigger.manual,
    options: RunStart | None = None,
) -> Run:
    """Queue a run. mode=single: one agent (optionally on a subset of the pages).
    mode=parallel: an orchestrator run that splits the pages over several sub-agents."""
    options = options or RunStart()
    if options.operation_key:
        existing = await session.scalar(
            select(Run).where(Run.org_id == org_id, Run.operation_key == options.operation_key)
        )
        if existing is not None:
            return existing
    task = await get_owned(session, Task, task_id, org_id)
    agent = await session.get(Agent, task.agent_id)
    if agent.status == AgentStatus.paused:
        raise Conflict(f"{agent.name} is paused. Resume the agent first.")
    reason = get_adapter(agent.runtime).check_ready()
    if reason:
        raise AppError(reason, code="runtime_not_ready")
    if await month_spend(session, agent.id) >= agent.monthly_budget_usd:
        raise Conflict(f"{agent.name} has used its monthly budget of ${agent.monthly_budget_usd}.")
    active = await session.scalar(select(Run.id).where(Run.task_id == task.id, Run.status.in_(ACTIVE)))
    if active:
        raise Conflict("This task already has an active run.")
    pages = [p.strip() for p in (options.pages or []) if p.strip()]
    run_options: dict = {"pages": pages} if pages else {}
    if options.max_turns:
        run_options["max_turns"] = options.max_turns
    if options.budget_usd:
        run_options["budget_usd"] = options.budget_usd
    kind = RunKind.single
    if options.mode == "parallel":
        s = get_settings()
        kind = RunKind.orchestrator
        run_options |= {
            "phase": "plan",
            "max_parallel": options.max_parallel or s.parallel_default_agents,
            "pages_per_agent": options.pages_per_agent,
            "max_turns": options.max_turns or s.subagent_max_turns,
            "budget_usd": options.budget_usd or s.subagent_budget_usd,
        }
    run = Run(
        org_id=org_id,
        task_id=task.id,
        agent_id=agent.id,
        trigger=trigger,
        created_by_id=user_id,
        kind=kind,
        options=run_options,
        operation_key=options.operation_key,
    )
    session.add(run)
    task.status = TaskStatus.in_progress
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if not options.operation_key:
            raise
        existing = await session.scalar(
            select(Run).where(Run.org_id == org_id, Run.operation_key == options.operation_key)
        )
        if existing is None:
            raise
        return existing
    await session.refresh(run)
    log.info(
        "run_queued",
        run_id=str(run.id)[:8],
        task=task.title,
        agent=agent.key,
        runtime=agent.runtime,
        trigger=trigger,
        kind=kind,
        options=run_options or None,
    )
    return run


async def list_runs(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None = None,
    status: RunStatus | None = None,
    limit: int = 50,
    top_level: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Run]:
    q = select(Run).where(Run.org_id == org_id)
    if since:
        q = q.where(Run.created_at >= since)
    if until:
        q = q.where(Run.created_at < until)
    if top_level:
        q = q.where(Run.parent_run_id.is_(None))
    if task_id:
        q = q.where(Run.task_id == task_id)
    if status:
        q = q.where(Run.status == status)
    return list(await session.scalars(q.order_by(Run.created_at.desc()).limit(limit)))


async def get_run(session: AsyncSession, org_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    return await get_owned(session, Run, run_id, org_id)


async def _cancel_one(session: AsyncSession, run: Run) -> None:
    if run.status in (RunStatus.queued, RunStatus.waiting_approval, RunStatus.waiting_children):
        run.status = RunStatus.cancelled
        run.ended_at = datetime.now(UTC)
        for ap in await session.scalars(
            select(Approval).where(Approval.run_id == run.id, Approval.status == "pending")
        ):
            ap.status = ApprovalStatus.rejected
            ap.comment = "Run was cancelled"
        task = await session.get(Task, run.task_id)
        task.status = TaskStatus.todo
    elif run.status == RunStatus.running:
        run.cancel_requested = True  # the worker stops it within a few seconds


async def cancel_run(session: AsyncSession, org_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = await get_run(session, org_id, run_id)
    if run.status in TERMINAL:
        raise Conflict(f"Run already {run.status}.")
    await _cancel_one(session, run)
    if run.kind == RunKind.orchestrator:  # stop every sub-agent too
        for child in await session.scalars(select(Run).where(Run.parent_run_id == run.id, Run.status.in_(ACTIVE))):
            await _cancel_one(session, child)
    await session.commit()
    log.info("run_cancel", run_id=str(run.id)[:8], status=run.status, kind=run.kind)
    if run.parent_run_id and run.status == RunStatus.cancelled:
        await maybe_queue_merge(session, run.parent_run_id)
    await session.refresh(run)
    return run


# ---------- parallel runs ----------


async def append_event(session: AsyncSession, run_id: uuid.UUID, type_: str, payload: dict) -> None:
    """Add a live-log event to a run that several processes write to (an orchestrator and its
    sub-agents). Locks the run row so the sequence numbers never collide. Caller commits."""
    await session.scalar(select(Run.id).where(Run.id == run_id).with_for_update())
    seq = await session.scalar(select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run_id))
    session.add(RunEvent(run_id=run_id, seq=seq + 1, type=type_, payload=payload))
    await session.flush()


async def maybe_queue_merge(session: AsyncSession, parent_id: uuid.UUID) -> bool:
    """When the last sub-agent of a parallel run ends, queue the orchestrator again to merge."""
    parent = await session.scalar(select(Run).where(Run.id == parent_id).with_for_update())
    if parent is None or parent.status != RunStatus.waiting_children:
        await session.rollback()
        return False
    active = await session.scalar(
        select(func.count()).select_from(Run).where(Run.parent_run_id == parent_id, Run.status.in_(ACTIVE))
    )
    if active:
        await session.rollback()
        return False
    parent.status = RunStatus.queued
    parent.options = {**parent.options, "phase": "merge"}
    await append_event(session, parent_id, "log", {"text": "All sub-agents finished. Merging their results…"})
    await session.commit()
    log.info("merge_queued", run_id=str(parent_id)[:8])
    return True


async def child_runs(session: AsyncSession, parent_id: uuid.UUID) -> list[Run]:
    q = select(Run).where(Run.parent_run_id == parent_id).order_by(Run.created_at)
    return list(await session.scalars(q))


async def run_events(session: AsyncSession, run_id: uuid.UUID, after_seq: int = 0, limit: int = 500) -> list[RunEvent]:
    q = select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after_seq).order_by(RunEvent.seq).limit(limit)
    return list(await session.scalars(q))


async def run_children(session: AsyncSession, model, run_ids: list[uuid.UUID]):
    q = select(model).where(model.run_id.in_(run_ids)).order_by(model.created_at)
    return list(await session.scalars(q))


async def chain_ids(session: AsyncSession, run: Run) -> list[uuid.UUID]:
    """A run and the runs it resumed: test cases and bugs live on the first run of the chain."""
    ids = [run.id]
    current = run
    while current.resumes_run_id:
        current = await session.get(Run, current.resumes_run_id)
        ids.append(current.id)
    return ids


async def result_run_ids(session: AsyncSession, run: Run) -> list[uuid.UUID]:
    """Runs whose results belong to this run: its resume chain, plus every sub-agent run of a
    parallel run."""
    ids = await chain_ids(session, run)
    if run.kind == RunKind.orchestrator:
        ids += [c.id for c in await child_runs(session, run.id)]
    return ids


async def run_test_cases(session: AsyncSession, run: Run) -> list[TestCase]:
    return await run_children(session, TestCase, await result_run_ids(session, run))


async def run_bugs(session: AsyncSession, run: Run) -> list[BugDraft]:
    return await run_children(session, BugDraft, await result_run_ids(session, run))


async def run_artifacts(session: AsyncSession, run: Run) -> list[Artifact]:
    return await run_children(session, Artifact, await result_run_ids(session, run))


async def get_artifact(session: AsyncSession, org_id: uuid.UUID, artifact_id: uuid.UUID) -> Artifact:
    art = await session.get(Artifact, artifact_id)
    if art is None:
        raise NotFound("Artifact not found")
    await get_run(session, org_id, art.run_id)
    return art


# ---------- approvals ----------


async def list_approvals(
    session: AsyncSession,
    org_id: uuid.UUID,
    status: ApprovalStatus | None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Approval]:
    q = select(Approval).where(Approval.org_id == org_id)
    if since:
        q = q.where(Approval.created_at >= since)
    if until:
        q = q.where(Approval.created_at < until)
    if status:
        q = q.where(Approval.status == status)
    return list(await session.scalars(q.order_by(Approval.created_at.desc()).limit(200)))


async def decide(
    session: AsyncSession,
    org_id: uuid.UUID,
    approval_id: uuid.UUID,
    user_id: uuid.UUID,
    approve: bool,
    comment: str,
    payload: dict | None = None,
    operation_key: str | None = None,
) -> tuple[Approval, Run | None]:
    ap = await session.scalar(
        select(Approval).where(Approval.id == approval_id, Approval.org_id == org_id).with_for_update()
    )
    if ap is None:
        raise NotFound("Approval not found.")
    if ap.status != ApprovalStatus.pending:
        if operation_key and ap.decision_key == operation_key:
            resume = await session.scalar(
                select(Run).where(Run.resumes_run_id == ap.run_id).order_by(Run.created_at.desc()).limit(1)
            )
            return ap, resume
        raise Conflict(f"Already {ap.status}.")
    paused = await session.get(Run, ap.run_id)
    task = await session.get(Task, paused.task_id)
    automatic = (task.scope or {}).get("discovery_mode") == "automatic"
    options = dict(paused.options or {})
    arguments = ap.payload.get("arguments") or {}
    if automatic and approve and ap.action in {"request_site_access", "browser_navigate"}:
        from app.runtime.qa_discovery import origin

        requested = origin(str(arguments.get("site") or arguments.get("url") or ""))
        options["qa_approved_origins"] = list(dict.fromkeys([*options.get("qa_approved_origins", []), requested]))
    if automatic and approve and ap.action == "request_budget_extension":
        from app.runtime.qa_discovery import continuation_options
        from app.runtime.tools import ToolError

        chosen = payload or arguments
        try:
            if float(chosen["budget_usd"]) > float(arguments["budget_usd"]) or int(chosen["max_turns"]) > int(
                arguments["max_turns"]
            ):
                raise ValueError
            continuation_options(options, cost=0, turns=0, extension=chosen)
        except (KeyError, TypeError, ValueError, ToolError) as exc:
            raise Conflict("Approve only the requested testing limit extension.") from exc
    paused.options = options
    ap.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    ap.decided_by_id = user_id
    ap.decided_at = datetime.now(UTC)
    ap.comment = comment
    ap.decision_key = operation_key
    if payload:
        ap.payload = {
            **ap.payload,
            "decision": {str(k)[:60]: str(v)[:4000] for k, v in payload.items()},
        }
    bug_id = (ap.payload.get("arguments") or {}).get("bug_id") if ap.action == "file_bug" else None
    if bug_id and not approve:
        bug = await session.get(BugDraft, uuid.UUID(bug_id))
        if bug:
            bug.status = BugStatus.rejected
    await session.flush()

    pending = await session.scalar(
        select(func.count()).select_from(Approval).where(Approval.run_id == ap.run_id, Approval.status == "pending")
    )
    resume = None
    if pending == 0:
        paused = await session.get(Run, ap.run_id)
        if paused.status == RunStatus.waiting_approval:
            if automatic and ap.action == "request_budget_extension" and not approve:
                from app.db.enums import TestCaseStatus

                paused.status = RunStatus.cancelled
                paused.ended_at = datetime.now(UTC)
                paused.summary = "Testing stopped by the manager at the approved limit. Partial results were kept."
                task.status = TaskStatus.blocked
                related_ids = [paused.id]
                parent_id = paused.resumes_run_id
                while parent_id and parent_id not in related_ids and len(related_ids) < 300:
                    related_ids.append(parent_id)
                    previous = await session.get(Run, parent_id)
                    parent_id = previous.resumes_run_id if previous else None
                for case in await session.scalars(
                    select(TestCase).where(TestCase.run_id.in_(related_ids), TestCase.status == TestCaseStatus.pending)
                ):
                    case.status = TestCaseStatus.skipped
                    case.notes = "Manager declined more testing."
                await session.commit()
                return ap, None
            if automatic:
                from app.runtime.qa_discovery import continuation_options

                extension = (payload or arguments) if ap.action == "request_budget_extension" and approve else None
                options = continuation_options(
                    options,
                    cost=float(paused.cost_usd),
                    turns=int((paused.result or {}).get("qa_turns", 0)),
                    extension=extension,
                )
            paused.status = RunStatus.succeeded
            paused.ended_at = paused.ended_at or datetime.now(UTC)
            paused.summary = paused.summary or "Paused for approval; continued in a follow-up run."
            resume = Run(
                org_id=org_id,
                task_id=paused.task_id,
                agent_id=paused.agent_id,
                trigger=RunTrigger.approval,
                resumes_run_id=paused.id,
                saved_state=paused.saved_state,
                created_by_id=user_id,
                kind=paused.kind,
                parent_run_id=paused.parent_run_id,
                options=options,
            )
            session.add(resume)
            task = await session.get(Task, paused.task_id)
            task.status = TaskStatus.in_progress
    await session.commit()
    log.info(
        "approval_decided",
        approval=str(ap.id)[:8],
        run_id=str(ap.run_id)[:8],
        action=ap.action,
        decision=ap.status,
        comment=comment[:200] or None,
        still_pending=pending,
    )
    if resume:
        await session.refresh(resume)
        log.info("resume_run_queued", run_id=str(resume.id)[:8], resumes=str(ap.run_id)[:8])
    return ap, resume


async def usage_summary(session: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    rows = await session.execute(
        select(
            Agent.id,
            Agent.name,
            Agent.monthly_budget_usd,
            func.count(Run.id),
            func.coalesce(func.sum(Run.input_tokens), 0),
            func.coalesce(func.sum(Run.output_tokens), 0),
            func.coalesce(func.sum(Run.cost_usd), 0),
        )
        .join(Run, Run.agent_id == Agent.id, isouter=True)
        .where(Agent.org_id == org_id)
        .group_by(Agent.id)
    )
    out = []
    for agent_id, name, budget, runs, tin, tout, cost in rows:
        out.append(
            {
                "agent_id": agent_id,
                "agent_name": name,
                "monthly_budget_usd": budget,
                "month_spend_usd": await month_spend(session, agent_id),
                "runs": runs,
                "input_tokens": tin,
                "output_tokens": tout,
                "total_cost_usd": cost,
            }
        )
    return out
