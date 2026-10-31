from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

DATABASE_URL = "postgresql+psycopg://prism:test@localhost:5432/prism_test"
FIXTURE_PATH = Path(__file__).parent / "fixtures/teams/v22_proactive_signal_scenarios.json"


def test_v22_feature_flag_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None, DATABASE_URL=DATABASE_URL)

    assert settings.prism_v22_enabled is False


def test_v22_foundation_is_hidden_when_feature_flag_is_off(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V22_ENABLED", "false")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/v2/prisms/foundation")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404


def test_v22_foundation_describes_available_phase_thirteen_capabilities(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("PRISM_V22_SINGLE_EXECUTIVE_MODE", "false")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/v2/prisms/foundation")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "release": "v2.2",
        "phase": 13,
        "single_executive_mode": False,
        "capabilities": [
            "feature-isolated multi-Prism release boundary",
            "durable private Prism identities and lifecycle audit",
            "private Prism directory, creation, and archive workflow",
            "resumable role-aware onboarding with validated answers",
            "reviewable working agreements with explicit activation",
            "isolated continuing conversation and memory for every active Prism",
            "durable Teams monitoring scope with local incremental activity reads",
            "durable local monitoring schedules and lease-claimed runs",
            "evidence-linked proactive Teams recommendations",
            "durable unread updates and open-page browser notifications",
            "conservative cross-Prism incident grouping with audited evolution",
            "approval-gated Teams drafts prepared from proactive updates",
            "feedback, signal tuning, run budgets, health diagnostics, and retention",
            "v2.1 conversation migration and operator recovery",
            "v2.1 regression compatibility",
        ],
        "excluded_capabilities": [
            "autonomous or approval-gated v2.2 actions",
        ],
    }


def test_v22_proactive_signal_fixture_covers_positive_negative_and_unsafe_cases() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())
    scenarios = {scenario["id"]: scenario for scenario in payload["scenarios"]}

    assert scenarios["production_incident_missing_owner"]["expected"]["should_alert"] is True
    assert scenarios["ordinary_chatter_no_alert"]["expected"]["should_alert"] is False
    assert scenarios["untrusted_instruction_no_policy_change"]["expected"] == {
        "should_alert": False,
        "must_not_change_policy": True,
        "must_not_create_action": True,
    }
