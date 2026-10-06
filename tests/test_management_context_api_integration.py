from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 after configuring DATABASE_URL to run PostgreSQL integration tests.",
)

from app.db.session import SessionLocal
from app.main import app
from app.models.management_context import ManagementContext
from app.services.management_context_service import ManagementContextService


def test_management_context_can_be_saved_and_listed() -> None:
    client = TestClient(app)
    title = "Test team context " + uuid.uuid4().hex[:12]
    entry_id: str | None = None
    try:
        created = client.post(
            "/api/v1/management-context",
            json={
                "category": "communication",
                "title": title,
                "content": "Keep follow-ups concise and ask for a concrete ETA.",
            },
        )
        assert created.status_code == 201
        entry_id = created.json()["id"]

        listed = client.get("/api/v1/management-context?limit=100")
        assert listed.status_code == 200
        assert any(item["id"] == entry_id for item in listed.json()["items"])

        updated = client.patch(
            "/api/v1/management-context/" + entry_id,
            json={
                "category": "team",
                "title": title + " updated",
                "content": "Use concise daily check-ins and ask for a concrete ETA.",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == title + " updated"

        deleted = client.delete("/api/v1/management-context/" + entry_id)
        assert deleted.status_code == 204
        entry_id = None
    finally:
        if entry_id is not None:
            with SessionLocal() as db:
                db.execute(delete(ManagementContext).where(ManagementContext.id == entry_id))
                db.commit()


def test_agent_context_is_active_relevant_and_bounded() -> None:
    suffix = uuid.uuid4().hex[:12]
    entry_ids: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            entries = [
                ManagementContext(
                    category="team",
                    title="Daily update guidance " + suffix,
                    content="Ask for a clear outcome and a concrete ETA.",
                ),
                ManagementContext(
                    category="work",
                    title="Deployment List " + suffix,
                    content="Riya\nOld unrelated deployment task. [ IN PROGRESS ]",
                ),
                ManagementContext(
                    category="person",
                    title="Riya ownership " + suffix,
                    content="Riya owns authentication decisions.",
                ),
                ManagementContext(
                    category="person",
                    title="Ajay ownership " + suffix,
                    content="Ajay owns schema changes.",
                ),
                ManagementContext(
                    category="team",
                    title="Inactive guidance " + suffix,
                    content="This must not reach the agent.",
                    is_active=False,
                ),
            ]
            db.add_all(entries)
            db.commit()
            entry_ids = [entry.id for entry in entries]

            context = ManagementContextService.agent_prompt_context(db, "Riya Sharma")

            assert context is not None
            assert "Ask for a clear outcome" in context
            assert "Riya owns authentication decisions" in context
            assert "Ajay owns schema changes" not in context
            assert "This must not reach the agent" not in context

            focused = ManagementContextService.agent_prompt_context(
                db, "Riya Sharma", query="The authentication dependency is blocked"
            )
            assert focused is not None
            assert "Riya owns authentication decisions" in focused
            assert "Old unrelated deployment task" not in focused
    finally:
        if entry_ids:
            with SessionLocal() as db:
                db.execute(delete(ManagementContext).where(ManagementContext.id.in_(entry_ids)))
                db.commit()
