"""Usage analytics: runs, cost, tokens, outcomes, per day / agent / model.

Computed in Python from the runs in the period: fine for thousands of runs; move to SQL
aggregates when volumes grow.
"""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, BugDraft, Run, TestCase
from app.services.runs import month_spend

FINAL_OK = {"succeeded"}
FINAL_BAD = {"failed", "timed_out"}


def _f(x) -> float:
    return float(x or 0)


async def analytics(
    session: AsyncSession,
    org_id: uuid.UUID,
    days: int = 30,
    agent_id: uuid.UUID | None = None,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Totals and breakdowns for runs created in [since, until). Without `since`: the last `days` days."""
    end = until or datetime.now(UTC)
    last_day = (end - timedelta(microseconds=1)).astimezone().date()
    if since is None:
        since = end - timedelta(days=days)
    else:
        days = max(1, (last_day - since.astimezone().date()).days + 1)
    q = select(Run).where(Run.org_id == org_id, Run.created_at >= since, Run.created_at < end)
    if agent_id:
        q = q.where(Run.agent_id == agent_id)
    runs = list(await session.scalars(q.order_by(Run.created_at)))
    run_ids = [r.id for r in runs]
    agents = {a.id: a for a in await session.scalars(select(Agent).where(Agent.org_id == org_id))}

    tests = list(await session.scalars(select(TestCase).where(TestCase.run_id.in_(run_ids)))) if run_ids else []
    bugs = list(await session.scalars(select(BugDraft).where(BugDraft.run_id.in_(run_ids)))) if run_ids else []
    bugs_by_run = Counter(b.run_id for b in bugs)

    def duration(r: Run) -> float | None:
        return (r.ended_at - r.started_at).total_seconds() if r.started_at and r.ended_at else None

    def summarise(rs: list[Run]) -> dict:
        durations = [d for d in (duration(r) for r in rs) if d is not None]
        cost = sum(_f(r.cost_usd) for r in rs)
        finished = [r for r in rs if r.status in FINAL_OK | FINAL_BAD]
        ok = sum(1 for r in rs if r.status in FINAL_OK)
        return {
            "runs": len(rs),
            "succeeded": ok,
            "failed": sum(1 for r in rs if r.status in FINAL_BAD),
            "cost_usd": round(cost, 4),
            "input_tokens": sum(r.input_tokens for r in rs),
            "output_tokens": sum(r.output_tokens for r in rs),
            "avg_cost_per_run": round(cost / len(rs), 4) if rs else 0,
            "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else 0,
            "success_rate": round(ok / len(finished), 3) if finished else 0,
            "bugs": sum(bugs_by_run[r.id] for r in rs),
        }

    # per day (every day in range, zeros included, for smooth charts)
    per_day: dict[date, list[Run]] = defaultdict(list)
    for r in runs:
        per_day[r.created_at.astimezone().date()].append(r)
    by_day = []
    for i in range(days - 1, -1, -1):
        d = last_day - timedelta(days=i)
        s = summarise(per_day.get(d, []))
        by_day.append(
            {
                "date": d.isoformat(),
                **{
                    k: s[k]
                    for k in ("runs", "succeeded", "failed", "cost_usd", "input_tokens", "output_tokens", "bugs")
                },
            }
        )

    by_agent = []
    for aid, rs in _group(runs, lambda r: r.agent_id).items():
        a = agents.get(aid)
        by_agent.append(
            {
                "agent_id": str(aid),
                "agent_name": a.name if a else "Deleted agent",
                "monthly_budget_usd": _f(a.monthly_budget_usd) if a else 0,
                "month_spend_usd": _f(await month_spend(session, aid)),
                **summarise(rs),
            }
        )

    by_model = [{"model": m or "unknown", **summarise(rs)} for m, rs in _group(runs, lambda r: r.model).items()]

    return {
        "period_days": days,
        "totals": {
            **summarise(runs),
            "tests_pass": sum(1 for t in tests if t.status == "pass"),
            "tests_fail": sum(1 for t in tests if t.status == "fail"),
            "tests_blocked": sum(1 for t in tests if t.status == "blocked"),
        },
        "by_day": by_day,
        "by_agent": sorted(by_agent, key=lambda x: -x["cost_usd"]),
        "by_model": sorted(by_model, key=lambda x: -x["cost_usd"]),
        "by_status": [{"status": k, "count": v} for k, v in Counter(r.status for r in runs).most_common()],
        "tests_by_status": [{"status": k, "count": v} for k, v in Counter(t.status for t in tests).most_common()],
        "bugs_by_severity": [
            {"severity": s, "count": sum(1 for b in bugs if b.severity == s)}
            for s in ("critical", "high", "medium", "low")
        ],
        "bugs_by_status": [{"status": k, "count": v} for k, v in Counter(b.status for b in bugs).most_common()],
    }


def _group(items, key):
    out = defaultdict(list)
    for i in items:
        out[key(i)].append(i)
    return out
