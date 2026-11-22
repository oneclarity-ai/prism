# 15 — Milestones Checklist

Build order: backend first, then UI, as agreed. Estimates assume 1–2 developers and are a starting point to adjust.

## Milestone 1 — Backend foundation (week 1)

- [x] 03: Tools installed, Postgres running in Docker
- [x] 04: FastAPI skeleton, settings, logging, health endpoints, worker entry point
- [x] 05: Models, first Alembic migration, seed script
- [x] 06: Auth, Agents, Targets, Secrets, Tasks endpoints with tests

**Exit:** create a target and a task through Swagger UI.

**Status (2026-10-13):** done. 21 API tests pass; Postgres runs locally (Homebrew) or via `docker compose`.

## Milestone 1.5 — Console UI for milestone 1 (added 2026-10-13)

- [x] 11: Vite + TS setup, generated API client, app shell, login
- [x] 12: Dashboard, Targets, Agents (overview, instructions, tools, tasks), Tasks (table, board, detail), Secrets
- [x] Placeholders for Runs, Approvals, Usage

**Status (2026-10-13):** done. Every backend feature from milestone 1 is usable in the browser. See [16-console-ui.md](16-console-ui.md) and features F-014 to F-026 in [17-feature-log.md](17-feature-log.md).

## Milestone 2 — Runs with a fake agent (week 2)

- [x] 07: `RuntimeAdapter` interface, registry, `FakeAdapter`
- [x] 08: Queue claim, worker loop, run lifecycle, cancel, timeout, recovery
- [x] 06: Runs, run events, artifacts endpoints; live updates via Server-Sent Events (changed from WebSocket, see 19 J-04)

**Exit:** start a run, watch fake events stream over WebSocket, cancel it.

**Status (2026-10-13):** done (SSE instead of WebSocket).

## Milestone 3 — Real QA agent (weeks 3–4)

- [x] 07: OpenAI Agents SDK adapter on Azure OpenAI with platform tools
- [x] 07: Playwright MCP locally (sandbox container still to do)
- [x] 09: QA `SKILL.md`, prompt template
- [x] 13: Eval app with seeded bugs
- [x] 10: Approvals for `file_bug`, budget caps, secret masking
- [x] Integrate GitHub Issues for filed bugs

**Exit:** the agent tests the eval app, finds bugs with screenshots, and files one after approval (via API calls only).

**Status (2026-10-13):** built and tested with a scripted model driving a real browser. A run with a real Azure model is waiting for the `AZURE_OPENAI_*` values. Guide: [20-live-agent-guide.md](20-live-agent-guide.md).

## Milestone 4 — React UI (weeks 5–6)

- [x] 11: Vite + TS setup, generated API client, app shell, login (done early in 1.5)
- [x] 11: Live stream client (SSE)
- [x] 12: Targets, Agents, Tasks, Task detail (done early in 1.5)
- [x] 12: Run live view and Run report
- [x] 12: Approvals inbox and Usage

**Exit:** full flow in the browser: new target → new task → live run → report → approve bug.

## Milestone 5 — Hardening and dogfooding (week 7)

- [ ] 13: CI tests, eval script and score table; hit MVP targets from 01
- [ ] 08: Schedules (nightly regression)
- [ ] 14: Docker images, staging deploy
- [ ] Run against one real OneClarity app for a week; collect feedback

**Exit:** QA agent used by the internal team on staging.

> **Updated plan (2026-10-14):** milestones 1–4 are done, plus parallel agents, cost controls and analytics. The current roadmap (M5 daily use → M6 deploy → M7 second agent → M8 manager agents) is in [28-roadmap.md](28-roadmap.md); it replaces the lists below.

## Next (after MVP)

- [ ] Claude Agent SDK adapter (optional) to prove the runtime is swappable
- [ ] Jira integration
- [ ] Trigger runs from GitHub PR / deploy webhooks
- [ ] Generate and save reusable Playwright test scripts from passing cases
- [ ] Langfuse tracing and eval dashboard
- [ ] Multi-tenancy (`org_id` already in place), SSO
- [ ] Next agent (Sales or Marketing) on the same platform
