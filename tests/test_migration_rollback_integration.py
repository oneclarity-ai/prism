"""Migrate the Phase 8 database shape to head, roll back, and migrate again.

Runs in a private Postgres schema so the configured database's real tables are never touched.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "prism_migration_check"
PHASE_8 = "20261028_0023"


def _url() -> str:
    source = os.getenv("DATABASE_URL") or dotenv_values(ROOT / ".env").get("DATABASE_URL")
    assert source, "DATABASE_URL is required for integration tests"
    base = make_url(source).set(query={}).render_as_string(hide_password=False)
    # Unencoded: alembic's ConfigParser rejects the '%' that URL-encoding would add.
    return f"{base}?options=-csearch_path={SCHEMA}"


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_phase_8_database_migrates_to_one_conversation_and_rolls_back_safely() -> None:
    url = _url()
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    try:
        _alembic(url, "upgrade", PHASE_8)

        first_thread, second_thread = uuid.uuid4(), uuid.uuid4()
        jobs = {first_thread: uuid.uuid4(), second_thread: uuid.uuid4()}
        with engine.connect() as connection:
            for index, (thread_id, job_id) in enumerate(jobs.items()):
                chat = f"legacy-chat-{index}"
                connection.execute(
                    text(
                        "INSERT INTO agent_threads (id, title, source_kind, source_external_id, "
                        "source_label, source_metadata, created_at, updated_at) VALUES "
                        "(:id, :title, 'teams_chat', :chat, :label, '{}'::jsonb, "
                        "now() + make_interval(secs => :offset), now())"
                    ),
                    {
                        "id": thread_id,
                        "title": f"Chat with person {index}",
                        "chat": chat,
                        "label": f"Person {index}",
                        "offset": index,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO agent_jobs (id, thread_id, goal, source_kind, "
                        "source_external_id, source_label, source_metadata, state, version, "
                        "created_at, updated_at) VALUES (:id, :thread, :goal, 'teams_chat', "
                        ":chat, :label, '{}'::jsonb, 'COMPLETED', 1, now(), now())"
                    ),
                    {
                        "id": job_id,
                        "thread": thread_id,
                        "goal": f"Review person {index}",
                        "chat": chat,
                        "label": f"Person {index}",
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO agent_thread_messages (id, thread_id, job_id, role, content, "
                        "message_metadata, created_at, updated_at) VALUES (:id, :thread, :job, "
                        "'manager', :content, '{}'::jsonb, now(), now())"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "thread": thread_id,
                        "job": job_id,
                        "content": f"History {index}",
                    },
                )

        _alembic(url, "upgrade", "head")
        with engine.connect() as connection:
            canonical = (
                connection.execute(text("SELECT id FROM agent_threads WHERE is_canonical"))
                .scalars()
                .all()
            )
            assert len(canonical) == 1
            assert connection.execute(text("SELECT count(*) FROM agent_threads")).scalar() == 1
            aliased = set(
                connection.execute(
                    text("SELECT legacy_thread_id FROM agent_thread_aliases")
                ).scalars()
            )
            assert aliased == {first_thread, second_thread}  # old deep links keep resolving
            assert (
                connection.execute(
                    text("SELECT count(*) FROM agent_jobs WHERE thread_id = :id"),
                    {"id": canonical[0]},
                ).scalar()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM agent_thread_messages WHERE thread_id = :id"),
                    {"id": canonical[0]},
                ).scalar()
                == 2
            )
            sources = connection.execute(
                text("SELECT external_id, selection_reason FROM agent_job_sources ORDER BY 1")
            ).all()
            assert sources == [
                ("legacy-chat-0", "legacy_selected"),
                ("legacy-chat-1", "legacy_selected"),
            ]

        # Rolling back must not lose the manager's history, and re-upgrading must still work.
        _alembic(url, "downgrade", PHASE_8)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM agent_jobs")).scalar() == 2
            assert (
                connection.execute(text("SELECT count(*) FROM agent_thread_messages")).scalar() == 2
            )
        _alembic(url, "upgrade", "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM agent_jobs")).scalar() == 2
            assert (
                connection.execute(
                    text("SELECT count(*) FROM agent_threads WHERE is_canonical")
                ).scalar()
                == 1
            )
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        engine.dispose()
