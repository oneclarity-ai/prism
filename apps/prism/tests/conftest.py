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
os.environ["TEAMS_CATALOG_CACHE_SECONDS"] = "0"  # tests bring their own Teams fakes
# v2.4 is on in .env for the manager; tests opt in so existing journeys keep their meaning.
os.environ["PRISM_V24_ENABLED"] = "false"

# Unit tests do not require a running PostgreSQL instance. Integration tests opt in
# with RUN_DB_TESTS=1 and use DATABASE_URL from the shell, or else a private
# `<name>_test` database next to the one in `.env`, so test rows (fake AI usage,
# Prisms, runs) never land in the manager's real data.
if os.getenv("RUN_DB_TESTS") != "1":
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@localhost:5432/prism_test",
    )
elif not os.getenv("DATABASE_URL"):
    import subprocess
    import sys
    from pathlib import Path

    from dotenv import dotenv_values
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    root = Path(__file__).resolve().parents[1]
    source = make_url(dotenv_values(root / ".env").get("DATABASE_URL") or "")
    name = f"{source.database}_test"
    admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if not connection.scalar(text("select 1 from pg_database where datname = :n"), {"n": name}):
            try:
                connection.execute(text(f'create database "{name}"'))
            except Exception as exc:
                raise RuntimeError(
                    f"Test database {name} is missing and this user can't create it. Run once: "
                    f"createdb -O {source.username} {name}"
                ) from exc
    admin.dispose()
    os.environ["DATABASE_URL"] = source.set(database=name).render_as_string(hide_password=False)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        check=True,
        capture_output=True,
    )
