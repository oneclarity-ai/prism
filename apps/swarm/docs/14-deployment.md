# 14 — Deployment

## Images

| Image | Contents |
| --- | --- |
| `oneclarity-api` | FastAPI app (uvicorn, 2+ workers) |
| `oneclarity-worker` | Same code base, runs `app.worker.main`; calls Azure OpenAI |
| `oneclarity-web` | Built React app served by nginx (or a CDN) |
| `oneclarity-playwright-mcp` | Node + `@playwright/mcp` + Chromium |

## Environments

| Env | Purpose | Notes |
| --- | --- | --- |
| local | development | docker compose, FakeAdapter by default, real adapter by flag |
| staging | internal dogfooding | real model, eval app + one real internal app |
| production | later | managed Postgres, S3 artifacts, secrets manager, HTTPS |

## Steps

1. Multi-stage Dockerfiles for backend and frontend.
2. GitHub Actions: lint (ruff, eslint), type check (mypy, tsc), tests, build images, push to registry.
3. Migrations run as a release step (`alembic upgrade head`) before new API pods start.
4. Artifacts: switch storage from local disk to S3-compatible bucket with signed URLs.
5. Observability: structlog to stdout → log platform; add OpenTelemetry + Langfuse traces for runs in a later milestone.
6. Backups: daily Postgres backup; artifact bucket lifecycle (e.g. 90 days).

## Done when

- Staging deploys from `main` automatically and a QA run works end to end there.
