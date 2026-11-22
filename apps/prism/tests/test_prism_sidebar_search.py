"""Search stays inside canonical Prism conversations and treats query wildcards literally."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.routes.prisms import prism_v22
from app.db.session import get_db
from app.services.prisms.prism_search_service import PrismSearchService


def test_prism_search_scopes_messages_and_escapes_wildcards():
    prism_id = uuid.uuid4()
    message_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    class Session:
        statements = []

        def scalars(self, statement):
            self.statements.append(statement)
            return [SimpleNamespace(id=prism_id, name="100% Prism", description="Planning")]

        def execute(self, statement):
            self.statements.append(statement)
            message = SimpleNamespace(
                id=message_id, role="manager", created_at=now, content="The task is 100% done."
            )
            return [(message, prism_id, "100% Prism")]

    session = Session()
    results = PrismSearchService.search(session, "100%")

    assert [item["kind"] for item in results] == ["prism", "message"]
    assert results[1]["prism_id"] == prism_id
    assert results[1]["message_id"] == message_id
    assert "100%" in results[1]["snippet"]
    for statement in session.statements:
        compiled = statement.compile(dialect=postgresql.dialect())
        assert "%100\\%%" in compiled.params.values()
        assert "prisms.state !=" in str(compiled)
    assert "agent_threads.is_canonical" in str(session.statements[1])
    assert "agent_thread_messages.role IN" in str(session.statements[1])


def test_prism_search_ignores_blank_query():
    class NoQuerySession:
        def scalars(self, _statement):
            raise AssertionError("Blank query reached the database")

    assert PrismSearchService.search(NoQuerySession(), "   ") == []


def test_search_route_precedes_prism_id_route(monkeypatch):
    monkeypatch.setattr(PrismSearchService, "search", staticmethod(lambda _db, _q: []))
    app = FastAPI()
    app.dependency_overrides[prism_v22.require_v22] = lambda: None
    app.dependency_overrides[get_db] = lambda: object()
    app.include_router(prism_v22.router)
    client = TestClient(app)

    assert client.get("/api/v2/prisms/search?q=ab").status_code == 200
    assert client.get("/api/v2/prisms/search?q=a").status_code == 422
