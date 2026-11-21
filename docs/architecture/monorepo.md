# Monorepo layout and migration

Date: 22 November 2026
Status: complete. Prism and the agentic swarm now live in this one repository.

## Why

Prism (the user-facing product) and the agentic swarm (the engine that runs computers, workers and
browser tests) were developed as two folders on one machine. The swarm was not under version control,
and Prism needed an absolute `SWARM_ROOT` path to start it. One repository gives a single place to
clone, review, version, test and document both, while keeping the runtime boundary unchanged.

## Layout

```text
prism/
├── apps/
│   ├── prism/                 Prism: FastAPI backend + static dashboard (port 8000)
│   │   ├── app/               application package (see "Prism package layout")
│   │   ├── alembic/           database migrations
│   │   ├── tests/             unit, API, PostgreSQL and e2e suites
│   │   ├── scripts/           prism_admin.py operator CLI
│   │   ├── Dockerfile, Makefile, pyproject.toml, requirements*.txt, .env.example
│   └── swarm/                 Agentic swarm engine (own stack, own database)
│       ├── backend/           FastAPI + worker + Alembic (API on port 8080 in dev)
│       ├── frontend/          React console (diagnostics only; Prism is the UI)
│       ├── eval-app/          Demo shop used by swarm evaluations
│       ├── docs/, diagrams/   swarm documentation
│       └── scripts/           swarm setup.sh / dev.sh
├── docs/
│   ├── architecture/          cross-cutting design (this file)
│   ├── adr/                   accepted architecture decisions
│   ├── guides/                handover, audits, design system, skills, navigation
│   ├── releases/              per-version plans, runbooks and the post-v2.4 change log
│   └── screenshots/
├── scripts/                   repo-level tools: dev.sh (run everything), check_secrets.py
├── .github/                   CI, security, CodeQL, Dependabot
├── compose.yaml               whole platform: Prism, its database, swarm API, worker, swarm database
├── Makefile                   root entry point; forwards Prism targets to apps/prism
└── README, CHANGELOG, AGENTS, ARCHITECTURE, CONTRIBUTING, SECURITY ...
```

Design rules taken from common large-repository practice: deployable units live under `apps/`; each app
owns its dependencies, tests, Dockerfile and config; cross-cutting docs and tooling live at the root;
nothing imports across apps. Prism reaches the swarm only through
`app/services/qa/qa_swarm_client.py` over HTTP (`QA_SWARM_*` settings), so the two codebases can still
be deployed, scaled and replaced independently.

## Prism package layout

`app/services`, `app/models`, `app/schemas` and `app/api/routes` are grouped by the same domains. A reader
who wants "how do Prisms work" opens `prisms/` in each layer.

| Domain | Contents |
| --- | --- |
| `prisms` | Prism lifecycle, onboarding, organization, skills, chat state, runs, notifications, recovery |
| `management` | Legacy manager assistant: tasks, projects, blockers, commitments, escalations, conversations, responses, intelligence, automation |
| `people` | Employees, aliases, people directory |
| `memory` | Temporal memory, Brain (shared knowledge), management context |
| `llm` | Providers, LLM calls and usage, provider credentials, Azure billing |
| `teams` | Microsoft Graph/OAuth, Teams reads, approved Teams execution |
| `qa` | QA plans, runs, spend, swarm client |
| `engine` | Prism computers, work bridge, work planning |

Shared kernel files stay at the layer root: `services/common.py`, `services/errors.py`,
`models/enums.py`, `schemas/common.py`, `api/routes/health.py`. The dashboard lives in
`app/static/` as `index.html`, `css/` and `js/` (`js/app.js` plus one module per feature).

## What changed in the migration

1. **Safety net.** The swarm folder (the only copy) was first backed up and put under git
   (baseline commit `b4eefd6`). Prism's uncommitted v2.4 work was committed as a checkpoint.
   Everything else happened on branch `monorepo` in a separate worktree, so the running servers were never
   touched until the new tree was verified.
2. **Import.** The swarm was imported with `git subtree add --prefix=apps/swarm`, which keeps its history.
   Its `.env`, `.venv`, `node_modules`, `var/` and build output are not tracked.
3. **Move Prism** into `apps/prism` with `git mv` (history preserved), plus `.env.example`, Makefile,
   Dockerfile and `prism_admin.py`.
4. **Tooling.** New root `Makefile`, `compose.yaml` (both stacks), `scripts/dev.sh` (replaces
   `scripts/dev_unified.sh`, no `SWARM_ROOT` needed), CI and Dependabot paths, and a VS Code workspace file.
5. **Domain grouping** of services (87 modules), models, schemas and routes, done by a script that moved
   files with `git mv` and rewrote every import, mock-patch string and dynamic module name. No class,
   function, route path, table or migration was renamed.
6. **Docs.** Flat `docs/` split into `guides/` and `releases/`; links rewritten and checked; README, AGENTS,
   CONTRIBUTING, ARCHITECTURE and the handover updated for the new paths.
7. **Dashboard tidy.** `styles.css` and `prism-theme.css` moved into `css/`, `app.js` into `js/`.
8. One pre-existing test (`test_models.py`) was missing the three skills tables; its list was corrected.

Not changed: public HTTP APIs, database schema, environment variable names, ports, and the Prism/swarm HTTP contract.

## Verification performed

| Check | Before | After |
| --- | --- | --- |
| Prism unit suite | 263 passed, 165 skipped | 263 passed, 165 skipped |
| Prism with PostgreSQL (`RUN_DB_TESTS=1`) | 428 passed | 428 passed |
| ruff, ruff format, mypy | clean | clean |
| Swarm backend tests | 78 passed (old folder) | 78 passed (`apps/swarm`) |
| API parity | live servers vs new tree | `/api/v2/prisms`, `/brain`, `/operations/overview`, `/qa/status` responses identical |
| Dashboard in Chrome | no console errors | no console errors, Brain page opens |
| Prism to swarm | n/a | `/api/v2/qa/status` reports available through the moved swarm |
| `docker compose config` | valid | valid (images were not built or started) |
| Browser e2e suite | not run | collects 90 tests; not executed (paused by request) |

## Running it

```bash
# first time
make setup                       # Prism venv (apps/prism/.venv)
make swarm-setup                 # swarm Python + Node dependencies
cp apps/prism/.env.example apps/prism/.env        # fill in
cp apps/swarm/backend/.env.example apps/swarm/backend/.env

make migrate                     # Prism schema
make dev-all                     # Prism :8000 + swarm API :8080 + worker
make check                       # lint, format, mypy, tests, secret scan (Prism)
make test-integration            # needs local PostgreSQL
```

Secrets stay in `apps/prism/.env` and `apps/swarm/backend/.env` (git-ignored). Compose additionally reads
`PRISM_DATABASE_PASSWORD` from a root `.env` or the shell.

## Cutover notes

- Existing Prism computers (Docker containers `prism-computer-*`) keep bind mounts to the swarm path they were
  created under. When you stop using `~/Downloads/agentic swarm`, remove the stopped containers once with
  `docker rm $(docker ps -aq --filter name=prism-computer)`. The swarm recreates each one on next use and keeps
  its named browser-profile volume (logins survive). Do this before deleting the old folder.
- Copy the git-ignored runtime data when moving a checkout: `apps/swarm/backend/var` (artifacts, computer work
  directories, logs) and `apps/swarm/var`, plus both `.env` files.
- Stop any dev servers started from the old folders before running `make dev-all` (ports 8000/8080).

## Rollback

- Branch `v2` before the migration is commit `c8e0372` (checkpoint); the original layout is intact there.
- Backups made before any move: `~/prism-backup-20261122.tgz` (Prism, without `.venv`) and
  `~/agentic-swarm-backup-20261122.tgz` (swarm, without `node_modules`/`.venv`).
- The original swarm folder in `~/Downloads/agentic swarm` was left untouched apart from the baseline git
  repository; it can be deleted once you are satisfied with `apps/swarm`.

## Conventions for future work

- New feature: add `service`, `model`, `schema` and `route` modules inside the matching domain package;
  create a new domain package only when no existing one fits, and update the table above.
- New app (for example a worker or an SDK): create `apps/<name>/` with its own README, tests and Dockerfile.
- Cross-app contracts are HTTP APIs documented in `docs/architecture/`; never import one app from another.
- Schema changes still need an Alembic migration in `apps/prism/alembic/versions/`.
