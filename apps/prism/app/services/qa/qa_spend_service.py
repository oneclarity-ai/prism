from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.llm.llm_usage import LLMUsage
from app.models.qa.qa import QaRun
from app.services.llm.llm_service import calculate_cost
from app.services.qa.qa_swarm_client import QaSwarmClient, SwarmError

logger = logging.getLogger(__name__)

PROVIDER = "qa_workspace"
# Runs a QA tester Prism started, and runs started in the testing workspace directly.
FEATURE_PRISM = "qa_tester_test_runs"
FEATURE_WORK = "prism_computer_tasks"  # tasks a Prism did on its own computer
FEATURE_OTHER = "qa_workspace_other_runs"
_UNSETTLED = {"queued", "running", "waiting_children"}
_KEY = "qa-run:"
# Rows written under an older pricing rule (or none) are re-synced once; bump this when the rule changes.
LEDGER_VERSION = 3


def _when(run: dict) -> datetime | None:
    value = run.get("ended_at") or run.get("started_at") or run.get("created_at")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None


class QaSpendService:
    """Copies the testing workspace's per-run AI spend into Prism's usage ledger.

    One row per workspace run, keyed by `request_id`, updated in place, so syncing again
    never double counts. Runs still in progress are left for a later sync.
    """

    @staticmethod
    def sync(db: Session, client: QaSwarmClient) -> int:
        latest = db.scalar(
            select(func.max(LLMUsage.timestamp)).where(LLMUsage.provider == PROVIDER)
        )
        stale = db.scalar(
            select(LLMUsage.id)
            .where(
                LLMUsage.provider == PROVIDER,
                or_(
                    LLMUsage.pricing_snapshot["v"].astext.is_(None),
                    LLMUsage.pricing_snapshot["v"].astext != str(LEDGER_VERSION),
                ),
            )
            .limit(1)
        )
        since = (latest - timedelta(days=2)).isoformat() if latest and not stale else None
        try:
            runs = client.runs(since=since)
        except SwarmError:
            return 0
        prism_runs: dict[str, str] = {}
        for ids, kind in db.execute(select(QaRun.swarm_run_ids, QaRun.kind)):
            for swarm_id in ids or []:
                prism_runs[str(swarm_id)] = kind
        existing = {
            row.request_id: row
            for row in db.scalars(
                select(LLMUsage).where(
                    LLMUsage.provider == PROVIDER,
                    LLMUsage.request_id.in_([_KEY + str(run["id"]) for run in runs]),
                )
            )
        }
        changed = 0
        for run in runs:
            if run.get("status") in _UNSETTLED:
                continue
            key = _KEY + str(run["id"])
            row = existing.get(key) or LLMUsage(provider=PROVIDER, request_id=key)
            inputs, outputs = int(run.get("input_tokens") or 0), int(run.get("output_tokens") or 0)
            cached = min(int(run.get("cached_input_tokens") or 0), inputs)
            model = str(run.get("model") or "qa-workspace")[:255]
            swarm_cost = Decimal(str(run.get("cost_usd") or 0))
            # Price the tokens with the same per-model table as Prism's own calls, so both
            # columns follow one rate card. Fall back to the swarm's own figure if unpriced.
            pricing = get_settings().llm_model_pricing.get(model)
            input_cost, output_cost, cost = calculate_cost(
                {
                    "prompt_tokens": inputs,
                    "completion_tokens": outputs,
                    "prompt_tokens_details": {"cached_tokens": cached},
                },
                pricing,
            )
            if cost is None:
                input_cost = output_cost = None
                cost = swarm_cost
            started, ended = run.get("started_at"), run.get("ended_at")
            latency = 0
            if started and ended:
                latency = int(
                    (_when({"ended_at": ended}) - _when({"ended_at": started})).total_seconds()
                    * 1000
                )
            values = {
                "timestamp": _when(run),
                "model": model,
                "deployment": model,
                "feature": {"qa": FEATURE_PRISM, "work": FEATURE_WORK}.get(
                    prism_runs.get(str(run["id"]), ""), FEATURE_OTHER
                ),
                "input_tokens": inputs,
                "cached_input_tokens": cached,
                "output_tokens": outputs,
                "total_tokens": inputs + outputs,
                "estimated_input_cost_usd": input_cost,
                "estimated_output_cost_usd": output_cost,
                "estimated_total_cost_usd": cost,
                "pricing_snapshot": {
                    "v": LEDGER_VERSION,
                    "source": "qa_workspace",
                    "status": run.get("status"),
                    "rates": pricing.model_dump() if pricing else None,
                    "swarm_cost_usd": str(swarm_cost),
                },
                "latency_ms": max(0, latency),
                "status": "completed" if run.get("status") == "succeeded" else "failed",
            }
            if any(getattr(row, name) != value for name, value in values.items()):
                for name, value in values.items():
                    setattr(row, name, value)
                db.add(row)
                changed += 1
        db.commit()
        if changed:
            logger.info("qa_spend_synced", extra={"runs": changed})
        return changed
