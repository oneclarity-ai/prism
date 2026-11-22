"""Parallel runs: split a task over several sub-agents, then merge their results.

An orchestrator run is executed twice by the worker:

1. phase "plan": split the task's pages into groups, create one sub-task per group (under the
   task, `tasks.parent_id`) and queue one sub-agent run per sub-task. The orchestrator then waits
   in status `waiting_children`; it holds no worker slot and no browser.
2. phase "merge": queued again by the last sub-agent to finish (`services.runs.maybe_queue_merge`).
   Collects test cases and bugs from every sub-agent, marks duplicate bugs, writes one final
   report and ends the run.

Planning is rule based (no model call). The merge makes at most one small model call for an
executive summary, only for agents on the Azure runtime.
"""

import math
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openai import AsyncAzureOpenAI
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import log
from app.db.enums import ArtifactKind, BugStatus, RunKind, RunStatus, TaskStatus
from app.db.models import Agent, Artifact, BudgetLedger, BugDraft, Run, Task, TestCase
from app.db.session import SessionLocal
from app.services.runs import TERMINAL, append_event, child_runs, current_period


def _now() -> datetime:
    return datetime.now(UTC)


class ParentEvents:
    """Live-log writer for a run that sub-agents also write to (see append_event)."""

    def __init__(self, run_id: uuid.UUID):
        self.run_id = run_id

    async def emit(self, type_: str, payload: dict) -> None:
        async with SessionLocal() as s:
            await append_event(s, self.run_id, type_, payload)
            await s.commit()
        if type_ in ("message", "status", "log"):
            log.info(f"run_{type_}", text=str(payload.get("status") or payload.get("text") or "")[:300])


# ---------- plan ----------


def split_scope(scope: dict[str, Any], pages: list[str], pages_per_agent: int, max_children: int) -> list[dict]:
    """Split a task scope into sub-agent assignments.

    Pages first (each sub-agent gets `pages_per_agent` pages; groups grow when there would be more
    than `max_children`). A task without pages is split by feature, then by acceptance criterion.
    """
    urls = pages or list(scope.get("urls") or [])
    features = list(scope.get("features") or [])
    criteria = list(scope.get("acceptance_criteria") or [])
    base = {
        "features": features,
        "acceptance_criteria": criteria,
        "allow_bug_filing": bool(scope.get("allow_bug_filing")),
    }

    def chunks(items: list[str]) -> list[list[str]]:
        size = max(pages_per_agent, math.ceil(len(items) / max_children))
        return [items[i : i + size] for i in range(0, len(items), size)]

    plans: list[dict] = []
    if urls:
        groups = chunks(urls)
        for i, group in enumerate(groups, 1):
            plans.append(
                {
                    "label": ", ".join(group),
                    "pages": group,
                    "scope": {
                        **base,
                        "urls": group,
                        "focus": (
                            f"You are sub-agent {i} of {len(groups)} in a parallel run. Test ONLY these pages: "
                            f"{', '.join(group)}. Other agents are testing the other pages at the same time, so "
                            "do not visit or test them. Apply the features and acceptance criteria only where "
                            "they concern your pages."
                        ),
                    },
                }
            )
    elif features or criteria:
        key, items = ("features", features) if features else ("acceptance_criteria", criteria)
        groups = chunks(items)
        for i, group in enumerate(groups, 1):
            plans.append(
                {
                    "label": "; ".join(group)[:120],
                    "pages": [],
                    "scope": {
                        **base,
                        "urls": [],
                        key: group,
                        "focus": (
                            f"You are sub-agent {i} of {len(groups)} in a parallel run. Test ONLY: "
                            f"{'; '.join(group)}. Other agents cover the rest at the same time."
                        ),
                    },
                }
            )
    else:
        plans.append({"label": "Whole task", "pages": [], "scope": {**base, "urls": [], "focus": ""}})
    return plans


async def plan(run_id: uuid.UUID) -> None:
    settings = get_settings()
    events = ParentEvents(run_id)
    async with SessionLocal() as s:
        run = await s.get(Run, run_id)
        task = await s.get(Task, run.task_id)
        opts = dict(run.options or {})
        plans = split_scope(
            dict(task.scope or {}),
            list(opts.get("pages") or []),
            int(opts.get("pages_per_agent") or 1),
            settings.parallel_max_children,
        )
    max_parallel = int(opts.get("max_parallel") or settings.parallel_default_agents)
    await events.emit("status", {"status": "running", "runtime": "orchestrator", "phase": "plan"})
    await events.emit(
        "message",
        {
            "role": "assistant",
            "kind": "comment",
            "text": (
                f"Orchestrator: splitting '{task.title}' into {len(plans)} sub-agent(s), "
                f"{max_parallel} working at once. Each sub-agent: up to {opts.get('max_turns')} turns, "
                f"${float(opts.get('budget_usd') or 0):.2f} budget, its own browser."
            ),
        },
    )

    async with SessionLocal() as s:
        run = await s.scalar(select(Run).where(Run.id == run_id).with_for_update())
        task = await s.get(Task, run.task_id)
        if run.cancel_requested:
            run.status, run.ended_at, run.error = RunStatus.cancelled, _now(), "Cancelled by a user."
            task.status = TaskStatus.todo
            await s.commit()
            return
        lanes = []
        for i, p in enumerate(plans, 1):
            title = f"{task.title} · {p['label']}"[:300]
            sub = await s.scalar(select(Task).where(Task.parent_id == task.id, Task.title == title).limit(1))
            if sub is None:
                sub = Task(
                    org_id=task.org_id,
                    title=title,
                    goal=task.goal,
                    agent_id=task.agent_id,
                    target_app_id=task.target_app_id,
                    parent_id=task.id,
                    created_by_id=run.created_by_id,
                )
                s.add(sub)
            sub.scope = p["scope"]
            sub.status = TaskStatus.in_progress
            await s.flush()
            child = Run(
                org_id=run.org_id,
                task_id=sub.id,
                agent_id=run.agent_id,
                trigger=run.trigger,
                created_by_id=run.created_by_id,
                kind=RunKind.child,
                parent_run_id=run.id,
                options={
                    "index": i,
                    "label": p["label"],
                    "pages": p["pages"],
                    "max_turns": opts.get("max_turns"),
                    "budget_usd": opts.get("budget_usd"),
                    "max_parallel": max_parallel,
                },
            )
            s.add(child)
            await s.flush()
            lanes.append({"index": i, "label": p["label"], "pages": p["pages"], "run_id": str(child.id)})
        run.status = RunStatus.waiting_children
        run.runtime = "orchestrator"
        run.model = "rule-based planner"
        await append_event(s, run.id, "plan", {"subagents": lanes, "max_parallel": max_parallel})
        await append_event(s, run.id, "status", {"status": RunStatus.waiting_children, "subagents": len(lanes)})
        await s.commit()
    log.info("parallel_planned", subagents=len(lanes), max_parallel=max_parallel)


# ---------- merge ----------

_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "on",
    "in",
    "of",
    "to",
    "and",
    "or",
    "not",
    "no",
    "with",
    "when",
    "for",
    "page",
    "allows",
    "allowed",
    "accepted",
    "accepts",
    "successful",
    "shows",
    "does",
}


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _STOP and len(w) > 1}


def find_duplicates(bugs: list[tuple[str, str]], threshold: float = 0.75) -> dict[str, str]:
    """Map duplicate bug id -> the first bug with a near-identical title.

    Two titles match when they share at least 3 meaningful words and those cover `threshold` of the
    shorter title. `bugs` is (id, title) in report order. Rule based on purpose: free, and good
    enough for "two agents saw the same broken login"."""
    kept: list[tuple[str, set[str]]] = []
    dupes: dict[str, str] = {}
    for bug_id, title in bugs:
        words = _words(title)
        match = None
        for kept_id, kept_words in kept:
            shared = len(words & kept_words)
            if shared >= 3 and shared / max(1, min(len(words), len(kept_words))) >= threshold:
                match = kept_id
                break
        if match:
            dupes[bug_id] = match
        else:
            kept.append((bug_id, words))
    return dupes


async def _executive_summary(agent: Agent, report_facts: str) -> tuple[str, float]:
    """One short model call that turns the merged facts into a few bullet points."""
    s = get_settings()
    if agent.runtime != "openai_agents" or not s.azure_configured:
        return "", 0.0
    from app.runtime.openai_agents import _cost, _is_reasoning_model  # avoid importing the SDK in tests

    deployment = agent.model or s.azure_openai_deployment
    client = AsyncAzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
        max_retries=s.azure_max_retries,
    )
    extra: dict[str, Any] = {}
    if _is_reasoning_model(deployment):
        extra = {"reasoning_effort": s.azure_reasoning_effort or "low", "max_completion_tokens": 2000}
    try:
        r = await client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": "You write the executive summary of a QA test report for an engineering manager. "
                    "4-6 short bullet points: overall verdict, the most important bugs, areas not tested or "
                    "blocked, and a recommended next step. Use only the facts given.",
                },
                {"role": "user", "content": report_facts[:12000]},
            ],
            **extra,
        )
    except Exception as exc:  # noqa: BLE001 - the report is complete without it
        log.warning("summary_call_failed", error=str(exc)[:300])
        return "", 0.0
    u = r.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return (r.choices[0].message.content or "").strip(), _cost(u.prompt_tokens, u.completion_tokens, cached)


async def merge(run_id: uuid.UUID) -> None:
    settings = get_settings()
    events = ParentEvents(run_id)
    await events.emit("status", {"status": "running", "runtime": "orchestrator", "phase": "merge"})
    async with SessionLocal() as s:
        run = await s.get(Run, run_id)
        task = await s.get(Task, run.task_id)
        agent = await s.get(Agent, run.agent_id)
        children = await child_runs(s, run.id)
        by_task: dict[uuid.UUID, list[Run]] = defaultdict(list)
        for c in children:
            by_task[c.task_id].append(c)
        all_ids = [c.id for c in children]
        cases = list(
            await s.scalars(select(TestCase).where(TestCase.run_id.in_(all_ids)).order_by(TestCase.created_at))
        )
        bugs = list(await s.scalars(select(BugDraft).where(BugDraft.run_id.in_(all_ids)).order_by(BugDraft.created_at)))

        run_lane = {}
        lanes = []
        for runs in by_task.values():
            first, last = runs[0], runs[-1]
            ids = {r.id for r in runs}
            for r in runs:
                run_lane[r.id] = first.options.get("index", 0)
            lane_cases = [c for c in cases if c.run_id in ids]
            lanes.append(
                {
                    "index": first.options.get("index", 0),
                    "label": first.options.get("label", ""),
                    "status": last.status,
                    "error": last.error,
                    "summary": last.summary,
                    "pass": sum(c.status == "pass" for c in lane_cases),
                    "fail": sum(c.status == "fail" for c in lane_cases),
                    "blocked": sum(c.status == "blocked" for c in lane_cases),
                    "total": len(lane_cases),
                    "bugs": sum(b.run_id in ids for b in bugs),
                    "cost": float(sum(r.cost_usd for r in runs)),
                }
            )
        lanes.sort(key=lambda lane: lane["index"])

        live_bugs = [b for b in bugs if b.status != BugStatus.rejected]
        dupes = find_duplicates([(str(b.id), b.title) for b in live_bugs])
        for b in live_bugs:
            b.duplicate_of_id = uuid.UUID(dupes[str(b.id)]) if str(b.id) in dupes else None
        unique = [b for b in live_bugs if str(b.id) not in dupes]
        await s.commit()

    # ---- report ----
    total = len(cases)
    n_pass = sum(c.status == "pass" for c in cases)
    n_fail = sum(c.status == "fail" for c in cases)
    n_blocked = sum(c.status == "blocked" for c in cases)
    sub_cost = sum(lane["cost"] for lane in lanes)
    ok_lanes = [lane for lane in lanes if lane["status"] == RunStatus.succeeded]
    verdict = (
        "FAILED: all sub-agents failed"
        if not ok_lanes
        else ("Bugs found" if unique or n_fail else ("Passed" if len(ok_lanes) == len(lanes) else "Partly tested"))
    )
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    lines = [
        f"## Final report: {task.title}",
        "",
        f"**Verdict: {verdict}.** {len(lanes)} sub-agents, {len(ok_lanes)} finished. "
        f"{total} test cases: {n_pass} passed, {n_fail} failed, {n_blocked} blocked. "
        f"{len(unique)} unique bug(s)" + (f" ({len(dupes)} duplicate(s) merged)" if dupes else "") + ".",
        "",
        "### Sub-agents",
        "",
        "| # | Area | Status | Cases (pass / fail / blocked) | Bugs | Cost |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for lane in lanes:
        lines.append(
            f"| {lane['index']} | {lane['label']} | {lane['status']} | {lane['pass']} / {lane['fail']} / "
            f"{lane['blocked']} of {lane['total']} | {lane['bugs']} | ${lane['cost']:.2f} |"
        )
    if unique:
        lines += ["", "### Bugs (duplicates merged)", ""]
        for b in sorted(unique, key=lambda b: sev_order.get(b.severity, 9)):
            lines.append(f"- **{b.severity}** · {b.title} _(sub-agent {run_lane.get(b.run_id, '?')})_")
    failed_cases = [c for c in cases if c.status in ("fail", "blocked")]
    if failed_cases:
        lines += ["", "### Failed or blocked cases", ""]
        for c in failed_cases:
            note = f": {c.notes}" if c.notes else ""
            lines.append(f"- {c.status.upper()} · {c.title} _(sub-agent {run_lane.get(c.run_id, '?')})_{note}")
    problems = [lane for lane in lanes if lane["status"] != RunStatus.succeeded]
    if problems:
        lines += ["", "### Sub-agents that did not finish", ""]
        for lane in problems:
            lines.append(f"- #{lane['index']} {lane['label']}: {lane['status']}. {lane['error'] or ''}".rstrip())
    lines += ["", "### Notes from each sub-agent", ""]
    for lane in lanes:
        if lane["summary"]:
            lines.append(f"- **#{lane['index']} {lane['label']}:** {lane['summary']}")

    report = "\n".join(lines)
    exec_summary, merge_cost = await _executive_summary(agent, report)
    if exec_summary:
        report = report.replace("### Sub-agents", f"### Executive summary\n\n{exec_summary}\n\n### Sub-agents", 1)
    report += f"\n\n_Total cost: ${sub_cost + merge_cost:.2f} (sub-agents ${sub_cost:.2f}, merge ${merge_cost:.3f})._"

    out_dir = settings.artifacts_dir / str(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "final-report.md"
    path.write_text(report, encoding="utf-8")

    status = RunStatus.succeeded if ok_lanes else RunStatus.failed
    async with SessionLocal() as s:
        run = await s.get(Run, run_id)
        task = await s.get(Task, run.task_id)
        s.add(
            Artifact(
                run_id=run.id,
                kind=ArtifactKind.report,
                path=str(path),
                mime="text/markdown",
                meta={"source": path.name},
            )
        )
        run.status = status
        run.ended_at = _now()
        run.summary = report
        run.error = None if ok_lanes else "All sub-agents failed. Open a sub-agent to see why."
        run.cost_usd = Decimal(str(round(merge_cost, 4)))
        if merge_cost > 0:
            s.add(
                BudgetLedger(
                    org_id=run.org_id,
                    agent_id=run.agent_id,
                    run_id=run.id,
                    period=current_period(),
                    cost_usd=Decimal(str(round(merge_cost, 4))),
                )
            )
        task.status = TaskStatus.done if ok_lanes else TaskStatus.failed
        await append_event(
            s,
            run.id,
            "status",
            {
                "status": status,
                "summary": f"{verdict}: {total} test cases, {len(unique)} unique bug(s). Full report above.",
                "error": run.error,
                "bugs": len(unique),
                "cases": total,
            },
        )
        await s.commit()
    log.info(
        "parallel_merged",
        status=status,
        subagents=len(lanes),
        cases=total,
        cases_fail=n_fail,
        bugs_unique=len(unique),
        bugs_duplicate=len(dupes),
        subagent_cost_usd=round(sub_cost, 4),
        merge_cost_usd=round(merge_cost, 4),
    )


async def execute_orchestrator(run_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        run = await s.get(Run, run_id)
        phase = (run.options or {}).get("phase", "plan")
    try:
        if phase == "merge":
            await merge(run_id)
        else:
            await plan(run_id)
    except Exception as exc:  # noqa: BLE001 - always end the run cleanly
        log.exception("orchestrator_crashed", phase=phase, error=str(exc))
        async with SessionLocal() as s:
            run = await s.get(Run, run_id)
            if run.status not in TERMINAL:
                run.status, run.ended_at, run.error = RunStatus.failed, _now(), f"{type(exc).__name__}: {exc}"
                task = await s.get(Task, run.task_id)
                task.status = TaskStatus.failed
            await s.commit()
