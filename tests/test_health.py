from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def test_root_returns_application_status() -> None:
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"name": "Yash Manager Agent", "status": "ok"}


def test_health_returns_healthy() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_database_health_executes_probe() -> None:
    class ProbeSession:
        def __init__(self) -> None:
            self.executed = False

        def execute(self, statement: object) -> None:
            self.executed = True
            assert str(statement) == "SELECT 1"

    probe_session = ProbeSession()
    app.dependency_overrides[get_db] = lambda: probe_session
    try:
        client = TestClient(app)
        response = client.get("/health/db")
    finally:
        app.dependency_overrides.clear()

    assert probe_session.executed is True
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
