# 04 — Backend Skeleton (FastAPI)

## Steps

1. **App factory** — `app/main.py` creates the FastAPI app, adds CORS for the Vite dev origin, mounts routers under `/api/v1`, and registers startup/shutdown for the DB engine.
2. **Settings** — `app/core/config.py` with `pydantic-settings`: `DATABASE_URL`, `AZURE_OPENAI_*`, `ARTIFACTS_DIR`, `CORS_ORIGINS`, `RUN_TIMEOUT_SEC`.
3. **Logging** — structlog JSON logs with `request_id` and `run_id` fields.
4. **DB session** — async SQLAlchemy engine + `get_session` dependency.
5. **Errors** — one exception handler that returns `{ "error": { "code", "message" } }`.
6. **Health** — `GET /api/v1/health` (app) and `GET /api/v1/health/db` (runs `SELECT 1`).
7. **Auth (simple)** — for the MVP, one admin user with email + password, JWT in an HTTP-only cookie. Keep it behind a `get_current_user` dependency so SSO can replace it later.
8. **Worker entry point** — `app/worker/main.py`, started as a separate process: `uv run python -m app.worker.main`.
9. **Docker Compose** — services `postgres`, `api`, `worker`, `playwright-mcp` (later), `eval-app` (later).

```yaml
services:
  postgres:
    image: postgres:16
    environment: { POSTGRES_USER: oc, POSTGRES_PASSWORD: oc, POSTGRES_DB: oneclarity }
    ports: ["5432:5432"]
    healthcheck: { test: ["CMD", "pg_isready", "-U", "oc"], interval: 5s }
  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    env_file: ./backend/.env
    depends_on: { postgres: { condition: service_healthy } }
    ports: ["8000:8000"]
  worker:
    build: ./backend
    command: python -m app.worker.main
    env_file: ./backend/.env
    depends_on: { postgres: { condition: service_healthy } }
```

## Done when

- `GET /api/v1/health/db` returns `{"status":"ok"}`.
- Swagger UI works at `http://localhost:8000/docs`.
- The worker process starts, logs "worker ready", and stops cleanly on Ctrl+C.
