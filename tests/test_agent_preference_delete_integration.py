from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.main import app


def test_a_preference_can_be_deleted_and_stays_gone(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        marker = uuid.uuid4().hex[:8]
        created = client.post(
            "/api/v2/agent/preferences",
            json={"instruction": f"Delete me {marker}", "scope": "general"},
        )
        assert created.status_code == 201
        preference_id = created.json()["id"]

        assert client.delete(f"/api/v2/agent/preferences/{preference_id}").status_code == 204
        listed = client.get("/api/v2/agent/preferences").json()
        assert preference_id not in {item["id"] for item in listed}
        assert client.delete(f"/api/v2/agent/preferences/{preference_id}").status_code == 404
    finally:
        get_settings.cache_clear()
