from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.llm_usage import LLMUsage
from app.services import azure_billing_service


def _row(provider, feature, model, cost, request_id):
    return LLMUsage(
        timestamp=datetime.now(timezone.utc),
        provider=provider,
        model=model,
        deployment=model,
        feature=feature,
        input_tokens=1000,
        cached_input_tokens=200,
        output_tokens=100,
        total_tokens=1100,
        estimated_total_cost_usd=Decimal(cost),
        latency_ms=1,
        status="completed",
        request_id=request_id,
    )


def test_sources_split_prism_from_swarm_and_keep_exact_cost():
    tag = uuid.uuid4().hex[:8]
    ids = [f"split-{tag}-{n}" for n in range(3)]
    with SessionLocal() as db:
        before = TestClient(app).get("/api/v1/usage/llm/sources?period=today").json()
        db.add_all(
            [
                _row("azure_openai", "prism_chat_reply", "gpt-5-nano", "0.0000123456", ids[0]),
                _row("qa_workspace", "prism_computer_tasks", "gpt-5-mini", "0.0004567891", ids[1]),
                _row("qa_workspace", "qa_tester_test_runs", "gpt-5-mini", "0.0001000000", ids[2]),
            ]
        )
        db.commit()
    try:
        after = TestClient(app).get("/api/v1/usage/llm/sources?period=today").json()

        def moved(source, field="estimated_cost_usd"):
            return Decimal(after["periods"]["today"][source][field]) - Decimal(
                before["periods"]["today"][source][field]
            )

        assert moved("prism") == Decimal("0.0000123456")  # six decimals survive, no rounding
        assert moved("swarm") == Decimal("0.0005567891")
        assert moved("swarm", "cached_input_tokens") == 400
        before_providers = {
            row["group"]: Decimal(row["estimated_cost_usd"]) for row in before["by_provider"]
        }
        after_providers = {
            row["group"]: Decimal(row["estimated_cost_usd"]) for row in after["by_provider"]
        }
        assert after_providers["azure_openai"] - before_providers.get("azure_openai", 0) == Decimal(
            "0.0000123456"
        )
        assert after_providers["qa_workspace"] - before_providers.get("qa_workspace", 0) == Decimal(
            "0.0005567891"
        )
        swarm_models = {row["group"] for row in after["by_model"]["swarm"]}
        assert "gpt-5-mini" in swarm_models and "gpt-5-nano" not in swarm_models
        assert "prism_computer_tasks" in {row["group"] for row in after["by_feature"]["swarm"]}
        assert "prism_computer_tasks" not in {row["group"] for row in after["by_feature"]["prism"]}
        assert after["timezone"] == get_settings().manager_timezone
    finally:
        with SessionLocal() as db:
            db.execute(delete(LLMUsage).where(LLMUsage.request_id.in_(ids)))
            db.commit()


def test_azure_billed_reports_not_configured_without_credentials():
    body = TestClient(app).get("/api/v1/usage/llm/azure-billed").json()
    assert body == {"configured": False, "sources": {}}


def test_azure_billing_sums_meters_and_survives_a_failing_source(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "azure_billing_tenant_id", "t")
    monkeypatch.setattr(settings, "azure_billing_client_id", "c")
    monkeypatch.setattr(
        settings,
        "azure_billing_client_secret",
        type("S", (), {"get_secret_value": lambda self: "x"})(),
    )
    monkeypatch.setattr(settings, "azure_billing_scopes", {"prism": "/a/b", "swarm": "/c/d"})
    azure_billing_service._cache.clear()

    def fake_query(scope, start, end):
        if scope == "/c/d":
            raise azure_billing_service.BillingError("Azure billing returned 403 for d.")
        return {
            "columns": [{"name": "Cost"}, {"name": "Meter"}, {"name": "Currency"}],
            "rows": [[0.5, "gpt-5-nano input", "USD"], [0.25, "gpt-5-nano output", "USD"]],
        }

    monkeypatch.setattr(azure_billing_service, "_query", fake_query)
    result = azure_billing_service.billed(
        datetime(2026, 11, 1).date(), datetime(2026, 11, 2).date()
    )
    assert result["sources"]["prism"]["cost"] == 0.75
    assert result["sources"]["prism"]["currency"] == "USD"
    assert result["sources"]["prism"]["meters"][0]["meter"] == "gpt-5-nano input"
    assert "403" in result["sources"]["swarm"]["error"]
    azure_billing_service._cache.clear()
