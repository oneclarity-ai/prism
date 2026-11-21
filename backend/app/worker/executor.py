"""Runs one heartbeat: claim, build context, call the runtime adapter, store the outcome."""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from app.computers.manager import ComputerManager
from app.core.logging import log
from app.db.enums import ApprovalStatus, RunKind, RunStatus, TaskStatus
from app.db.models import (
    Agent,
    Approval,
    BudgetLedger,
    BugDraft,
    Run,
    RunEvent,
    TargetApp,
    Task,
    TestCase,
)
from app.runtime.base import AgentSpec, Decision, RunCancelled, RunContext, RunResult, TaskSpec
from app.runtime.registry import get_adapter
from app.runtime.tools import PlatformTools
from app.services.runs import append_event, chain_ids, current_period, maybe_queue_merge
from app.worker.heartbeat import WORKER_ID
from app.worker.orchestrator import execute_orchestrator
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.db.session import SessionLocal


def _now() -> datetime:
    return datetime.now(UTC)


class EventWriter:
    """Appends run events with a gap-free sequence number."""

    def __init__(self, run_id: uuid.UUID, start_seq: int):
        self.run_id = run_id
        self.seq = start_seq
        self.lock = asyncio.Lock()

    async def emit(self, type_: str, payload: dict) -> None:
        async with self.lock:
            self.seq += 1
            async with SessionLocal() as s:
                s.add(RunEvent(run_id=self.run_id, seq=self.seq, type=type_, payload=payload))
                await s.commit()
        if type_ in ("message", "status", "log"):
            text = payload.get("status") or payload.get("text") or ""
            log.info(f"run_{type_}", seq=self.seq, text=str(text)[:300])
        else:
            log.debug("run_event", seq=self.seq, type=type_, tool=payload.get("tool"))


async def claim_next() -> uuid.UUID | None:
    """Oldest queued run. A sub-agent waits while its parallel run already has `max_parallel`
    sub-agents running (protects the Azure rate limit and the machine)."""
    sibling = aliased(Run)
    running_siblings = (
        select(func.count())
        .select_from(sibling)
        .where(sibling.parent_run_id == Run.parent_run_id, sibling.status == RunStatus.running)
        .correlate(Run)
        .scalar_subquery()
    )
    other = aliased(Run)
    agent_busy = (
        select(1)
        .select_from(other)
        .where(other.agent_id == Run.agent_id, other.status == RunStatus.running, other.id != Run.id)
        .correlate(Run)
        .exists()
    )
    has_computer = (
        select(1)
        .select_from(Agent)
        .where(
            Agent.id == Run.agent_id,
            Agent.tool_grants["computer"].astext.is_not(None),
            Agent.tool_grants["computer"].astext != "off",
        )
        .correlate(Run)
        .exists()
    )
    async with SessionLocal() as s:
        run = await s.scalar(
            select(Run)
            .where(
                Run.status == RunStatus.queued,
                # One computer = one task at a time: wait while the same agent has a run going.
                or_(~has_computer, ~agent_busy),
                or_(
                    Run.parent_run_id.is_(None),
                    running_siblings < func.coalesce(Run.options["max_parallel"].as_integer(), 1000),
                ),
            )
            .order_by(Run.created_at)
            .with_for_update(skip_locked=True, of=Run)
            .limit(1)
        )
        if run is None:
            return None
        token = uuid.uuid4()
        run.status = RunStatus.running
        run.started_at = run.started_at or _now()  # a parallel run is claimed twice (plan, merge)
        run.lease_owner = WORKER_ID
        run.lease_token = token
        run.lease_expires_at = _now() + timedelta(seconds=get_settings().run_lease_seconds)
        run.attempt += 1
        await s.commit()
        waited = (run.started_at - run.created_at).total_seconds()
        log.info(
            "run_claimed",
            run_id=str(run.id)[:8],
            kind=run.kind,
            trigger=run.trigger,
            waited_in_queue_s=round(waited, 1),
        )
        return run.id


async def recover_stale() -> None:
    """Reclaim expired safe checkpoints; stop when an outward tool may have happened."""
    settings = get_settings()
    async with SessionLocal() as s:
        uncertain = await s.execute(
            update(Run)
            .where(
                Run.status == RunStatus.running,
                or_(
                    Run.lease_expires_at.is_(None),
                    (Run.lease_expires_at < _now()) & Run.active_tool_risky.is_(True),
                ),
            )
            .values(
                status=RunStatus.failed,
                ended_at=_now(),
                error="outcome_unknown: worker ownership was lost during a possible action; it was not retried.",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
            .returning(Run.id, Run.task_id)
        )
        recoverable = await s.execute(
            update(Run)
            .where(
                Run.status == RunStatus.running,
                Run.lease_expires_at < _now(),
                Run.active_tool_risky.is_(False),
            )
            .values(
                status=RunStatus.queued,
                error=None,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                active_tool=None,
            )
            .returning(Run.id, Run.task_id)
        )
        expired = await s.execute(
            update(Run)
            .where(
                Run.status == RunStatus.waiting_approval,
                Run.updated_at < _now() - timedelta(hours=settings.approval_timeout_hours),
            )
            .values(status=RunStatus.cancelled, ended_at=_now(), error="approval_timeout")
            .returning(Run.id, Run.task_id)
        )
        uncertain_rows = uncertain.all()
        recoverable_rows = recoverable.all()
        expired_rows = expired.all()
        if uncertain_rows:
            await s.execute(
                update(Task)
                .where(Task.id.in_([row.task_id for row in uncertain_rows]))
                .values(status=TaskStatus.failed)
            )
        if expired_rows:
            expired_run_ids = [row.id for row in expired_rows]
            await s.execute(
                update(Approval)
                .where(
                    Approval.run_id.in_(expired_run_ids),
                    Approval.status == ApprovalStatus.pending,
                )
                .values(status=ApprovalStatus.rejected, comment="Approval expired")
            )
            await s.execute(
                update(Task).where(Task.id.in_([row.task_id for row in expired_rows])).values(status=TaskStatus.todo)
            )
        await s.commit()
        n_uncertain, n_recovered, n_expired = (
            len(uncertain_rows),
            len(recoverable_rows),
            len(expired_rows),
        )
        waiting = list(await s.scalars(select(Run.id).where(Run.status == RunStatus.waiting_children)))
    if n_uncertain or n_recovered or n_expired:
        log.warning(
            "recovered_runs",
            outcome_unknown=n_uncertain,
            requeued=n_recovered,
            approvals_expired=n_expired,
        )
    # Parallel runs whose sub-agents all ended while no worker was running still need their merge.
    for parent_id in waiting:
        async with SessionLocal() as s:
            await maybe_queue_merge(s, parent_id)


async def _load(run_id: uuid.UUID):
    async with SessionLocal() as s:
        run = await s.get(Run, run_id)
        agent = await s.get(Agent, run.agent_id)
        task = await s.get(Task, run.task_id)
        target = await s.get(TargetApp, task.target_app_id) if task.target_app_id else None
        related = await chain_ids(s, run)
        last_seq = await s.scalar(select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run.id))
        decisions = []
        if run.resumes_run_id:
            for ap in await s.scalars(select(Approval).where(Approval.run_id == run.resumes_run_id)):
                decisions.append(
                    Decision(
                        call_id=ap.payload.get("call_id", ""),
                        approved=ap.status == ApprovalStatus.approved,
                        comment=ap.comment,
                        payload=dict(ap.payload.get("decision") or {}),
                    )
                )
        return run, agent, task, target, related, last_seq, decisions


async def execute_run(run_id: uuid.UUID) -> None:
    settings = get_settings()
    structlog.contextvars.bind_contextvars(run_id=str(run_id)[:8])  # task-local: every line of this run carries it
    run, agent, task, target, related, last_seq, decisions = await _load(run_id)
    lease_token = run.lease_token
    if lease_token is None:
        log.warning("run_missing_lease", run_id=str(run_id)[:8])
        return
    if run.kind == RunKind.orchestrator:
        await execute_orchestrator(run.id)
        return
    opts = dict(run.options or {})
    scope = dict(task.scope or {})
    if opts.get("pages"):
        scope["urls"] = list(opts["pages"])  # this run tests only the chosen pages
    automatic = scope.get("discovery_mode") == "automatic"
    if automatic:
        scope["_qa_limits"] = {
            "budget_usd": opts.get("qa_budget_limit", opts.get("budget_usd", agent.run_budget_usd)),
            "max_turns": opts.get("qa_turn_limit", opts.get("max_turns", agent.max_turns)),
        }
        if run.resumes_run_id:
            async with SessionLocal() as previous_session:
                previous_run = await previous_session.get(Run, run.resumes_run_id)
                scope["_qa_coverage"] = (previous_run.result or {}).get("qa_coverage", {}) if previous_run else {}
    max_turns = int(opts.get("max_turns") if opts.get("max_turns") is not None else agent.max_turns)
    budget_usd = float(opts.get("budget_usd") if opts.get("budget_usd") is not None else agent.run_budget_usd)
    events = EventWriter(run.id, last_seq)
    grants = dict(agent.tool_grants or {})
    if automatic and scope.get("request_login"):
        # The approved QA plan grants secure login requests for this task, not other Prism work.
        grants.update(request_login="ask_first", sign_in="allowed")
    computer_key = agent.key if grants.get("computer", "off") != "off" else None
    if computer_key:
        work_dir = ComputerManager.work_dir(computer_key)  # the folder the computer's browser writes to
    else:
        work_dir = (settings.artifacts_dir.parent / "work" / str(run.id)).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    tools = PlatformTools(
        run.id,
        run.org_id,
        task.id,
        work_dir,
        related_run_ids=related,
        scope=scope,
        computer_key=computer_key,
    )

    baseline = {
        "input": run.input_tokens,
        "output": run.output_tokens,
        "cached": run.cached_input_tokens,
        "cost": Decimal(run.cost_usd),
    }
    last_check = {"at": 0.0, "value": False}

    async def is_cancelled() -> bool:
        if time.monotonic() - last_check["at"] < 2:
            return last_check["value"]
        async with SessionLocal() as s:
            row = (await s.execute(select(Run.cancel_requested, Run.lease_token).where(Run.id == run.id))).one_or_none()
            last_check["value"] = row is None or bool(row.cancel_requested) or row.lease_token != lease_token
        last_check["at"] = time.monotonic()
        return last_check["value"]

    async def mark_tool_started(tool: str, risky: bool) -> None:
        async with SessionLocal() as s:
            result = await s.execute(
                update(Run)
                .where(
                    Run.id == run.id,
                    Run.lease_token == lease_token,
                    Run.status == RunStatus.running,
                )
                .values(active_tool=tool[:120], active_tool_risky=risky)
            )
            if result.rowcount != 1:
                raise RunCancelled()
            await s.commit()

    async def checkpoint(state: dict, usage: dict) -> None:
        async with SessionLocal() as s:
            result = await s.execute(
                update(Run)
                .where(
                    Run.id == run.id,
                    Run.lease_token == lease_token,
                    Run.status == RunStatus.running,
                )
                .values(
                    saved_state=state,
                    result={
                        "qa_coverage": getattr(tools, "qa_coverage", scope.get("_qa_coverage", {})),
                        "qa_turns": getattr(tools, "qa_turns", 0),
                    }
                    if automatic
                    else run.result,
                    checkpoint_at=_now(),
                    active_tool=None,
                    active_tool_risky=False,
                    input_tokens=baseline["input"] + int(usage.get("input_tokens", 0)),
                    output_tokens=baseline["output"] + int(usage.get("output_tokens", 0)),
                    cached_input_tokens=baseline["cached"] + int(usage.get("cached_tokens", 0)),
                    cost_usd=baseline["cost"] + Decimal(str(usage.get("cost_usd", 0))),
                )
            )
            if result.rowcount != 1:
                raise RunCancelled()
            await s.commit()

    ctx = RunContext(
        run_id=str(run.id),
        agent=AgentSpec(
            id=str(agent.id),
            key=agent.key,
            name=agent.name,
            instructions=agent.instructions,
            model=agent.model,
            tool_grants=dict(agent.tool_grants or {}),
            max_turns=max_turns,
            run_budget_usd=budget_usd,
        ),
        task=TaskSpec(
            id=str(task.id),
            title=task.title,
            goal=task.goal,
            scope=scope,
            target_name=target.name if target else None,
            target_url=target.base_url if target else None,
            target_environment=target.environment if target else None,
            target_notes=target.notes if target else None,
            has_test_login=bool(target and target.auth_secret_id),
            extra_origins=(
                list(opts.get("qa_approved_origins") or [])
                if automatic
                else list(target.extra_origins or [])
                if target
                else []
            ),
        ),
        work_dir=work_dir,
        tools=tools,
        emit=events.emit,
        is_cancelled=is_cancelled,
        saved_state=run.saved_state,
        decisions=decisions,
        computer_key=computer_key,
        mark_tool_started=mark_tool_started,
        checkpoint=checkpoint,
    )

    async def renew_lease() -> None:
        interval = max(2.0, settings.run_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            async with SessionLocal() as s:
                result = await s.execute(
                    update(Run)
                    .where(
                        Run.id == run.id,
                        Run.lease_token == lease_token,
                        Run.status == RunStatus.running,
                    )
                    .values(lease_expires_at=_now() + timedelta(seconds=settings.run_lease_seconds))
                )
                await s.commit()
                if result.rowcount != 1:
                    return

    renew_task = asyncio.create_task(renew_lease())

    async with SessionLocal() as s:
        await s.execute(
            update(Run)
            .where(Run.id == run.id)
            .values(
                runtime=agent.runtime,
                model="scripted" if agent.runtime == "fake" else (agent.model or settings.azure_openai_deployment),
            )
        )
        await s.commit()
    log.info(
        "run_started",
        runtime=agent.runtime,
        agent=agent.key,
        model=agent.model or settings.azure_openai_deployment,
        task=task.title,
        target=target.base_url if target else None,
        resume_of=str(run.resumes_run_id)[:8] if run.resumes_run_id else None,
        decisions=[f"{d.call_id}:{'approve' if d.approved else 'reject'}" for d in decisions] or None,
        max_turns=max_turns,
        run_budget_usd=budget_usd,
        pages=scope.get("urls") or None,
        parent=str(run.parent_run_id)[:8] if run.parent_run_id else None,
        work_dir=str(work_dir),
    )
    if run.parent_run_id:
        verb = "resumed after approval on" if run.resumes_run_id else "started on"
        await _tell_parent(run, f"{verb} {opts.get('label') or task.title}", "running")
    await events.emit(
        "status",
        {"status": "running", "runtime": agent.runtime, "resume": bool(run.resumes_run_id)},
    )
    try:
        try:
            adapter = get_adapter(agent.runtime)
            result = await asyncio.wait_for(adapter.execute(ctx), timeout=settings.run_timeout_sec)
        except TimeoutError:
            result = RunResult(status="timed_out", error=f"Run exceeded {settings.run_timeout_sec} seconds.")
        except RunCancelled:
            result = RunResult(status="cancelled", error="Cancelled by a user.")
        except Exception as exc:  # noqa: BLE001 - every failure must end the run cleanly
            log.exception("run_crashed", error=str(exc))
            result = RunResult(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        renew_task.cancel()
        await asyncio.gather(renew_task, return_exceptions=True)

    if result.status != "waiting_approval":
        reason = (
            f"the run ended before this case was executed ({result.error})"
            if result.error
            else "the agent finished without executing this case"
        )
        try:
            closed = await tools.close_pending_cases(reason[:500])
            if closed:
                await events.emit(
                    "log",
                    {"text": f"{closed} planned case(s) were never run and are marked skipped."},
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("close_pending_failed", error=str(exc))

    # Screenshots taken right before the end are still collected.
    try:
        for img in await tools.collect_new_images():
            await events.emit("artifact", {"kind": "screenshot", **img})
    except Exception as exc:  # noqa: BLE001
        log.warning("artifact_collect_failed", error=str(exc))

    await finalize(
        run.id,
        lease_token,
        baseline,
        result,
        tools.completed,
        events,
        qa_progress={
            "qa_coverage": getattr(tools, "qa_coverage", scope.get("_qa_coverage", {})),
            "qa_turns": getattr(tools, "qa_turns", 0),
        }
        if automatic
        else None,
    )


async def finalize(
    run_id: uuid.UUID,
    lease_token: uuid.UUID,
    baseline: dict,
    result: RunResult,
    completed: dict | None,
    events: EventWriter,
    qa_progress: dict | None = None,
) -> None:
    async with SessionLocal() as s:
        run = await s.scalar(select(Run).where(Run.id == run_id, Run.lease_token == lease_token).with_for_update())
        if run is None:
            log.warning("run_finalize_fenced", run_id=str(run_id)[:8])
            return
        task = await s.get(Task, run.task_id)
        run.status = result.status
        run.input_tokens = baseline["input"] + result.input_tokens
        run.output_tokens = baseline["output"] + result.output_tokens
        run.cached_input_tokens = baseline["cached"] + result.cached_tokens
        run.cost_usd = baseline["cost"] + Decimal(str(round(result.cost_usd, 10)))
        run.lease_owner = None
        run.lease_token = None
        run.lease_expires_at = None
        run.active_tool = None
        run.active_tool_risky = False
        run.summary = result.summary or run.summary
        if completed and (completed.get("results") or completed.get("files")):
            run.result = {
                "outcome": completed.get("outcome"),
                "results": completed.get("results") or [],
                "files": completed.get("files") or [],
            }
        if qa_progress is not None:
            run.result = {**(run.result or {}), **qa_progress}
        run.error = result.error
        if result.status == RunStatus.waiting_approval:
            run.saved_state = result.saved_state
        else:
            run.ended_at = _now()

        for item in result.interruptions:
            payload = {"call_id": item.call_id, "tool": item.tool, "arguments": item.arguments}
            if item.tool == "file_bug" and item.arguments.get("bug_id"):
                bug = await s.get(BugDraft, uuid.UUID(item.arguments["bug_id"]))
                if bug:
                    payload["bug"] = {
                        "id": str(bug.id),
                        "title": bug.title,
                        "severity": bug.severity,
                        "steps": bug.steps,
                        "expected": bug.expected,
                        "actual": bug.actual,
                    }
                    payload["title"] = bug.title
            s.add(Approval(org_id=run.org_id, run_id=run.id, action=item.tool, payload=payload))

        if result.cost_usd > 0:
            s.add(
                BudgetLedger(
                    org_id=run.org_id,
                    agent_id=run.agent_id,
                    run_id=run.id,
                    period=current_period(),
                    cost_usd=run.cost_usd,
                )
            )

        if result.status == RunStatus.succeeded:
            task.status = TaskStatus.blocked if completed and completed.get("outcome") == "blocked" else TaskStatus.done
        elif result.status in (RunStatus.failed, RunStatus.timed_out):
            task.status = TaskStatus.failed
        elif result.status == RunStatus.cancelled:
            task.status = TaskStatus.todo
        elif result.status == RunStatus.waiting_approval:
            task.status = TaskStatus.blocked
        await s.commit()

    await events.emit(
        "status",
        {
            "status": result.status,
            "error": result.error,
            "summary": result.summary,
            "approvals": len(result.interruptions),
        },
    )
    async with SessionLocal() as s:
        cases = list(await s.scalars(select(TestCase.status).where(TestCase.run_id == run_id)))
        bugs = await s.scalar(select(func.count()).select_from(BugDraft).where(BugDraft.run_id == run_id))
        run = await s.get(Run, run_id)
    if run.parent_run_id:
        text = (
            f"{result.status}: {len(cases)} cases ({cases.count('fail')} failed), {bugs} bug(s), ${result.cost_usd:.2f}"
        )
        if result.error:
            text += f". {result.error[:200]}"
        await _tell_parent(run, text, result.status)
        if result.status != RunStatus.waiting_approval:
            async with SessionLocal() as s:
                await maybe_queue_merge(s, run.parent_run_id)
    log.info(
        "run_finished",
        status=result.status,
        error=result.error,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=round(result.cost_usd, 4),
        cases_pass=cases.count("pass"),
        cases_fail=cases.count("fail"),
        cases_blocked=cases.count("blocked"),
        bugs=bugs,
        approvals_requested=len(result.interruptions),
    )


async def _tell_parent(run: Run, text: str, status: str) -> None:
    """Mirror a sub-agent's start and end into the parallel run's live log."""
    index = (run.options or {}).get("index", "?")
    async with SessionLocal() as s:
        await append_event(
            s,
            run.parent_run_id,
            "subagent",
            {
                "index": index,
                "run_id": str(run.id),
                "status": status,
                "text": f"Sub-agent {index} {text}",
            },
        )
        await s.commit()
