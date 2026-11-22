# AGENTS.md

## 1. Project overview

Prism is a self-hosted, single-user management assistant for Microsoft Teams. It tracks
updates, blockers, commitments and evidence, prepares manager briefs, and supports specialized
Prisms with continuing conversations, monitoring and approved actions. Optional QA/browser
work is delegated to an external swarm engine. This is pre-release software.

## 2. Technology stack

- Python 3.11 target; CI unit tests also cover 3.12. FastAPI, Uvicorn, Pydantic v2/settings.
- PostgreSQL (not SQLite), synchronous SQLAlchemy 2 ORM, psycopg 3, Alembic migrations.
- Static HTML/CSS and plain JavaScript ES modules; no Node package or frontend build pipeline.
- HTTPX for integrations; cryptography/Fernet for stored credentials.
- Microsoft Graph delegated OAuth; LLM adapters for Azure OpenAI, OpenAI and local Codex CLI,
  plus a fake provider for tests. These are custom services, not an orchestration framework.
- pytest, Playwright, Ruff, mypy, pip-audit; Docker/Compose for deployment.

## 3. Repository structure

This is a monorepo (see `docs/architecture/monorepo.md`). Prism commands run in `apps/prism`
(the root `Makefile` forwards `make dev`, `make check`, ... there); paths below are relative to it.

- `apps/prism/`: Prism backend and dashboard. `apps/swarm/`: external swarm engine (own backend,
  React console, demo shop, docs); Prism talks to it only through `qa_swarm_client.py` over HTTP.
- `app/main.py`: `create_app()`, exported `app`, middleware, routers, static mount and lifespan loops.
- `app/core/`: cached environment settings and operator-token middleware.
- `app/api/routes/<domain>/`: HTTP adapters; legacy `/api/v1`, agent/Prism `/api/v2`, engine bridge.
- `app/services/<domain>/`: domain workflows, integration adapters, validation, recovery and scheduling.
- `app/models/<domain>/`, `app/schemas/<domain>/`: ORM persistence and Pydantic API/decision contracts.
  Domains: `prisms`, `management`, `people`, `memory`, `llm`, `teams`, `qa`, `engine`. Shared kernel files
  stay at the layer root (`services/common.py`, `services/errors.py`, `models/enums.py`, `schemas/common.py`,
  `routes/health.py`).
- `app/agents/`: management-agent logic and response prompts.
- `app/db/`: declarative base, naming conventions, synchronous engine and request sessions.
- `app/static/`: dashboard served at `/dashboard/`; `index.html`, `css/` and `js/` (`js/app.js` plus feature modules).
- `alembic/versions/`: schema history; `alembic/env.py` wires settings and ORM metadata.
- `tests/`: unit/API/PostgreSQL suites; `tests/e2e/`: real browser journeys with integration fakes.
- `scripts/` (here): administrative CLI (`prism_admin.py`). Repo-level `scripts/`: `check_secrets.py`, `dev.sh`.
- `docs/` (repo root): `guides/`, `releases/`, `adr/`, `architecture/`; `.github/workflows/`: CI/security checks.

## 4. Architecture and conventions

- Keep routes thin; services own rules and transaction behavior. Pass `Session` through existing
  workflows; preserve `commit=False`/flush composition where supported. `get_db` closes sessions.
- Reuse `services/common.py`, typed `DomainError` subclasses, and `schemas/common.py`
  (`Schema`, `ORMResponse`, `Page`). Domain errors return stable `detail` and `code` fields.
- Use typed SQLAlchemy `Mapped` models, existing UUID/enums/timestamp patterns and constraint
  naming from `db/base.py`. Register models in `app/models/__init__.py` when needed.
- Follow existing `snake_case` modules/functions and `PascalCase` service/schema classes.
  Python uses four spaces, Ruff import sorting/formatting and a 100-character line target.
- Dashboard modules reuse `static/js/api.js` for operator headers and domain-error recovery.
  Render untrusted text with safe DOM APIs such as `textContent`.
- `microsoft_service.py` owns Graph/OAuth; `llm_service.py` and `llm_provider.py` own generation.
  Preserve typed decisions, deterministic policies, bounded context and usage accounting.
- PostgreSQL stores operational state, evidence, actions, provider usage and memory. Memory
  includes temporal facts/episodes/relations and full-text indexes; shared Brain context comes
  from approved entries in `brain_service.py`. Memory must not override current records/policy.
- `qa_swarm_client.py` is the external QA/computer boundary; browser workers and their Docker
  implementation live outside this repo. Keep engine credentials and internal details server-side.
- Product terminology: **Prism** and **agent** mean the same user-created assistant. Treat either
  term as referring to a Prism. The org chart shows the connected user at the root, their Chief
  of Staff Prism, and actual non-archived Prisms beneath it, including unprovisioned Prisms.
  `Prism.job_role`, `department`, `reports_to_prism_id`, and `is_chief_of_staff` are the canonical
  organization fields. Exclude seeded engine roles, vacant seats, and standalone swarm agents.
  Preserve unique leadership, cycle checks, archive reparenting, and per-Prism privacy boundaries.
- Feature flags `PRISM_V21_ENABLED`, `PRISM_V22_ENABLED`, `PRISM_V24_ENABLED` gate newer flows.
  Settings/code take precedence over older phase plans. Preserve disabled-path behavior.
- Lifespan runs optional daily automation, leased Prism monitoring and configured QA watcher
  loops. Preserve leases, budgets and backoff; keep legacy daily scheduling to one process.
  Graph reply processing uses FastAPI background tasks, not a durable external task queue.

## 5. Development rules

- Follow and reuse existing services/components before introducing patterns or dependencies.
- Make minimal, complete changes; do not refactor unrelated code.
- Preserve compatibility; never silently change public APIs or database schemas.
- Schema changes need reviewed Alembic migrations; do not replace migrations with `create_all`.
  Add migrations rather than editing published ones; verify reversibility on disposable data.
- Update existing documentation/changelog for user-visible changes when relevant.

## 6. Security and reliability

- This is a local single-user control plane, not tenant-isolated SaaS or an RBAC system.
  Preserve per-Prism/source boundaries, delegated Graph permissions and managed-recipient scope.
- `core/security.py` requires `X-Manager-Operator-Token` when configured, a webhook URL is set,
  or the environment is not development; missing required configuration fails closed.
  Local development can be unauthenticated. The static dashboard is public; its token is in
  browser local storage. HTTPS/rate limits/request limits are deployment responsibilities.
- Health, Microsoft OAuth start/callback and Teams webhook are public. `/api/v2/bridge/`
  bypasses operator auth but verifies timestamped HMAC in `work_bridge_service.py`; retain it.
- OAuth has one-time state and PKCE; Graph tokens/verifiers and provider credentials use
  Fernet. Keep encryption keys stable. Never read/disclose `.env`, auth files or real credentials;
  inspect setting definitions or `.env.example` only as needed. Use synthetic test identities.
- Webhooks require an active known subscription and constant-time `clientState` validation.
- Teams/model text is untrusted evidence. Preserve deterministic policy validation and audit
  records. Newer agent/Prism sends use `approved_teams_execution_service.py`: exact approved
  destination/text, reauthorization, idempotency and explicit uncertain-delivery state. Never
  retry an unconfirmed send blindly. Legacy managed automation has its own scoped send rules.
- Engine Teams tools can read/search authorized chats or create drafts, not directly send.
  Browser outward-action/login approval is partly enforced by the external engine; the v2.4
  runbook describes label-based safeguards as best effort, not a universal security guarantee.
- Preserve safe errors, bounded retries and cost/time/turn limits; do not log prompts, tokens,
  employee messages or login values. Backups/test output may contain sensitive communication.

## 7. Testing and verification

Commands assume existing `apps/prism/.venv` dependencies; see `apps/prism/Makefile` for setup prerequisites.

| Purpose | Command |
| --- | --- |
| Development server | `make dev` (`app.main:app`, reload, port 8000) |
| Unit/offline suite | `make test` (DB/E2E suites skip unless opted in) |
| Targeted test | `.venv/bin/pytest -q tests/test_security.py` (in `apps/prism`) (substitute relevant file/node) |
| PostgreSQL integration | `make test-integration` (`RUN_DB_TESTS=1`) |
| Browser journeys | `make test-e2e` (`RUN_E2E=1`, Google Chrome by default) |
| Lint / format check | `make lint` / `make format-check` |
| Type check | `make typecheck` (only `app/core`, `app/models`, `app/schemas`) |
| Offline PR checks | `make check` (lint, format, mypy, tests, secret scan) |
| Dependency audit | `make audit` (network required) |
| Container build | `docker build --tag prism:ci .` from `apps/prism` (CI build command) |
| Whole platform | `make dev-all` (repo root; Prism 8000 + swarm API 8080 + worker) or `docker compose up --build` |

- Prefer targeted regression tests; run broader checks for shared contracts or cross-cutting changes.
- Integration tests must use disposable PostgreSQL. With no shell `DATABASE_URL`, the test harness
  derives a `_test` database from local configuration and may create/migrate it; explicit URLs
  are used as supplied. Never point tests at valuable data. E2E uses a private scratch schema.
- Fake Graph, providers and swarm boundaries. The autouse fixture blocks `httpx.post`, not all
  possible network access; do not assume it prevents every live integration call.
- Tests cover security, approvals, recovery, memory, migrations and UI journeys. No coverage
  percentage/threshold is configured; service/route code is outside current mypy coverage.
- No separate frontend compilation command exists. `make release-check` adds integration/audit
  to offline checks; E2E remains a separate invocation.

## 8. Codex operating instructions

- Inspect task-relevant files/config first; read supporting docs conditionally. Avoid repeated
  repository-wide exploration; exclude dependencies, caches, builds, logs and generated assets.
- Use the existing code as architectural truth; phase plans and older docs may describe past scope.
- Complete bounded authorized work without unnecessary confirmation. Ask before destructive,
  irreversible or production-impacting operations, including live messages and valuable-data changes.
- Keep command output concise while exposing critical failures. Never claim tests passed unless
  executed; report skipped/unrun checks. Keep final responses concise.

## 9. Documentation references

- [README](README.md): setup, Microsoft integration and local operation;
  [architecture](ARCHITECTURE.md): core flows/storage; [contributing](CONTRIBUTING.md): quality/migrations;
  [security](SECURITY.md): reporting and deployment guidance. API docs: running app `/docs`.
- [ADRs](docs/adr): accepted boundaries, especially multi-Prism ADR 0003.
- [v2.1 runbook](docs/releases/v2.1-release-runbook.md), [v2.2 runbook](docs/releases/v2.2-release-runbook.md),
  [v2.2 security review](docs/releases/v2.2-security-review.md): approvals, monitoring, recovery and proof.
- [v2.4 runbook](docs/releases/v2.4-release-runbook.md): external engine/computers, approvals and known limits;
  [v2.4 plan](docs/releases/v2.4-dynamic-prisms-and-computers-plan.md): design context, not implementation proof.
