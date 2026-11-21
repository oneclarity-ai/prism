"""Automatic website planning and safe projections, without live integrations."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.errors import RuleViolationError
from app.services.qa_plan_service import QaPlanDraft, QaPlanService
from app.services.qa_run_service import QaRunService


def test_url_alone_discovers_pages_despite_model_requesting_routes(monkeypatch):
    monkeypatch.setattr(QaPlanService, "house_rules", lambda *a: ([], False))
    monkeypatch.setattr(
        "app.services.llm_service.LLMService.complete",
        lambda **kw: QaPlanDraft(
            pages=["/invented-dashboard"], needs_clarification=True, question="Which routes?"
        ),
    )
    plan = QaPlanService.build(
        Mock(),
        prism=SimpleNamespace(id="p", name="QA"),
        thread_id="t",
        text="Test https://example.invalid/pricing",
    )
    assert plan["pages"] == ["/pricing"]
    assert plan["discovery_mode"] == "automatic"
    assert plan["allowed_origins"] == ["https://example.invalid"]
    assert plan["request_login"] and plan["request_budget_extension"]
    assert "Ask before payments" in plan["notes"]


@pytest.mark.parametrize(
    "site",
    ["javascript:alert(1)", "https://user:secret@example.invalid", "https://example.invalid:bad"],
)
def test_approval_origin_rejects_non_web_and_embedded_credentials(site):
    with pytest.raises(RuleViolationError):
        QaRunService._qa_origin(site)


def test_new_site_and_budget_cards_keep_exact_scope_and_limits():
    run = SimpleNamespace(plan={"budget_usd": 1, "max_turns": 60})
    kind, view, _ = QaRunService._approval_view(
        run,
        "request_site_access",
        {"site": "https://app.example.invalid/login", "reason": "Sign in"},
        {},
    )
    assert kind == "site_access" and view["site"] == "https://app.example.invalid"
    kind, view, _ = QaRunService._approval_view(
        run, "request_budget_extension", {"budget_usd": 999, "max_turns": 9999}, {}
    )
    assert kind == "budget_extension"
    assert view["budget_usd"] < 999 and view["max_turns"] < 9999


def test_report_does_not_count_visits_or_planned_routes_as_tests(monkeypatch):
    monkeypatch.setattr(QaRunService, "_all_cases", lambda *a: [])
    monkeypatch.setattr(QaRunService, "_summary", lambda *a: "Partial test")
    run = SimpleNamespace(
        plan={
            "host": "example.invalid",
            "environment": "production",
            "pages": ["/invented"],
            "discovery_mode": "automatic",
        },
        state="cancelled",
        cases={
            "coverage": {
                "pages": [
                    {"url": "https://example.invalid/", "status": "tested"},
                    {"url": "https://example.invalid/login", "status": "visited"},
                    {
                        "url": "https://example.invalid/admin",
                        "status": "blocked",
                        "reason": "Login declined",
                    },
                ]
            }
        },
        swarm_run_ids=[],
        started_at=None,
        ended_at=None,
        cost_usd=0,
        turn=4,
        screenshot_ids=[],
    )
    report = QaRunService._build_report(Mock(), run, Mock(), {})
    assert report["pages"] == ["https://example.invalid/"]
    assert report["partial"] and len(report["untested_pages"]) == 2
    assert report["untested_pages"][1]["reason"] == "Login declined"


def test_empty_starting_routes_reset_to_root_without_disabling_discovery():
    result = QaPlanService.apply_edits(
        {"pages": ["/old"], "discovery_mode": "automatic"}, {"pages": []}
    )
    assert result["pages"] == ["/"] and result["discovery_mode"] == "automatic"
