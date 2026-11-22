from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app


def test_provider_status_api_never_returns_credentials(monkeypatch) -> None:
    class EmptySession:
        def scalar(self, _statement):
            return None

    monkeypatch.setenv("INTELLIGENCE_LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-returned")
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", "test")
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: EmptySession()
    try:
        response = TestClient(app).get("/api/v1/provider/status")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "model": "test-model",
        "state": "ready",
        "ready": True,
        "detail": "Ready",
        "credential_source": "environment",
        "masked_key": None,
        "can_manage": True,
    }
    assert "must-not-be-returned" not in response.text
