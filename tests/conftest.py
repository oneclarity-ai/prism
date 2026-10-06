import os
import pytest


@pytest.fixture(autouse=True)
def no_live_http_posts(monkeypatch):
    """Tests must supply explicit provider/Graph fakes, never use .env credentials."""
    def reject(*args, **kwargs):
        raise AssertionError("Live HTTP POST is disabled in tests; mock the provider")
    monkeypatch.setattr("httpx.post", reject)

# Tests use the local control-plane mode by default. Individual security tests
# explicitly enable a token and clear the settings cache.
os.environ["MICROSOFT_WEBHOOK_BASE_URL"] = ""
os.environ["OPERATOR_API_TOKEN"] = ""
os.environ["INTELLIGENCE_LLM_ENABLED"] = "false"

# Unit tests do not require a running PostgreSQL instance. Integration tests opt in
# with RUN_DB_TESTS=1 and then use DATABASE_URL from the shell or `.env`.
if os.getenv("RUN_DB_TESTS") != "1":
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@localhost:5432/yash_manager_test",
    )
