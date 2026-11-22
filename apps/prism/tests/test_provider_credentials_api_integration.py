from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.services.llm.provider_credential_service import ProviderCredentialService


def _reset(*provider_ids: str) -> None:
    with SessionLocal() as db:
        for provider_id in provider_ids:
            ProviderCredentialService.remove(db, provider_id=provider_id)


def test_credentials_list_save_and_remove_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    get_settings.cache_clear()
    _reset("anthropic", "deepseek")
    try:
        client = TestClient(app)

        listed = client.get("/api/v1/provider/credentials").json()
        by_id = {item["provider"]: item for item in listed}
        assert set(by_id) == {"openai", "azure_openai", "anthropic", "deepseek", "custom"}
        assert by_id["anthropic"]["is_active_provider"] is True
        assert by_id["anthropic"]["configured"] is False
        assert by_id["azure_openai"]["needs_base_url"] is True

        saved = client.put(
            "/api/v1/provider/credentials/anthropic",
            json={"api_key": "sk-ant-byok-test-key-0000000000", "model": "claude-sonnet-5-5"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["configured"] is True
        assert body["masked_key"].endswith("0000")
        assert "sk-ant" not in body["masked_key"]

        status = client.get("/api/v1/provider/status").json()
        assert status["provider"] == "anthropic"
        assert status["credential_source"] == "database"
        assert "sk-ant-byok-test-key-0000000000" not in str(status)

        removed = client.delete("/api/v1/provider/credentials/anthropic")
        assert removed.status_code == 204
        listed_after = client.get("/api/v1/provider/credentials").json()
        assert next(i for i in listed_after if i["provider"] == "anthropic")["configured"] is False
    finally:
        get_settings.cache_clear()
        _reset("anthropic", "deepseek")


def test_azure_openai_credential_requires_a_base_url(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    _reset("azure_openai")
    try:
        client = TestClient(app)
        response = client.put(
            "/api/v1/provider/credentials/azure_openai",
            json={"api_key": "azure-byok-test-key-0000000000", "model": "gpt-5-nano"},
        )
        assert response.status_code == 422
    finally:
        get_settings.cache_clear()
        _reset("azure_openai")


def test_unknown_provider_id_is_a_404(monkeypatch) -> None:
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        response = client.put(
            "/api/v1/provider/credentials/not-a-real-provider",
            json={"api_key": "a-long-enough-fake-key-00000000", "model": "x"},
        )
        assert response.status_code == 404
    finally:
        get_settings.cache_clear()


def test_credential_test_endpoint_reports_a_rejected_key_without_saving(monkeypatch) -> None:
    import httpx

    def get(_url, **_kwargs):
        return httpx.Response(401, json={})

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.get", get)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/provider/credentials/openai/test",
            json={"api_key": "sk-not-a-real-key-but-long-enough", "model": "gpt-4o-mini"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": False, "detail": "The API key was rejected"}

        listed = client.get("/api/v1/provider/credentials").json()
        assert next(i for i in listed if i["provider"] == "openai")["configured"] is False
    finally:
        get_settings.cache_clear()
