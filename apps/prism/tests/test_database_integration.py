import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app


def test_database_session_executes_select_one() -> None:
    with SessionLocal() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_database_health_endpoint() -> None:
    response = TestClient(app).get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
