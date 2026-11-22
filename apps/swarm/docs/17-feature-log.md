# 17 — Feature Log

Every feature gets a number when it is built. Add new rows at the bottom; never renumber. "Plan ref" points to the plan file that describes it.

| # | Feature | Layer | Milestone | Plan ref | Status | Date |
| --- | --- | --- | --- | --- | --- | --- |
| F-001 | FastAPI app factory, settings from `.env`, JSON logs with secret redaction, request ids | Backend | 1 | 04 | Done | 2026-10-13 |
| F-002 | Uniform error format `{error: {code, message}}` | Backend | 1 | 04 | Done | 2026-10-13 |
| F-003 | Health checks `/health`, `/health/db` | Backend | 1 | 04 | Done | 2026-10-13 |
| F-004 | Data model: 13 tables + organizations, first Alembic migration | Backend | 1 | 05 | Done | 2026-10-13 |
| F-005 | Seed script: organization, admin user, QA agent with skill and tool grants | Backend | 1 | 05, 09 | Done | 2026-10-13 |
| F-006 | Login / logout / me with HTTP-only session cookie (Bearer also accepted) | Backend | 1 | 04, 06 | Done | 2026-10-13 |
| F-007 | Agents API: list, create, get, update, pause, resume | Backend | 1 | 06 | Done | 2026-10-13 |
| F-008 | Secrets API: write-only, Fernet-encrypted at rest | Backend | 1 | 06, 10 | Done | 2026-10-13 |
| F-009 | Target apps API with encrypted test login | Backend | 1 | 06 | Done | 2026-10-13 |
| F-010 | Tasks API with scope, filters and status | Backend | 1 | 06 | Done | 2026-10-13 |
| F-011 | Worker process entry point (start, DB check, clean stop) | Backend | 1 | 08 | Done | 2026-10-13 |
| F-012 | Azure OpenAI smoke test script (`scripts/check_azure.py`) | Backend | 1 | 03 | Done (needs your keys) | 2026-10-13 |
| F-013 | 21 API tests + ruff lint | Backend | 1 | 13 | Done | 2026-10-13 |
| F-014 | Frontend project: Vite + React + TS, shadcn/ui, Tailwind, Geist fonts, brand theme, dark mode | Frontend | 1.5 | 11, 16 | Done | 2026-10-13 |
| F-015 | Typed API client generated from OpenAPI; query/mutation hooks with toasts | Frontend | 1.5 | 11, 16 | Done | 2026-10-13 |
| F-016 | Login screen (split brand panel, validation, show password) | Frontend | 1.5 | 16.1 | Done | 2026-10-13 |
| F-017 | App shell: collapsible sidebar, breadcrumbs, auth guard, user menu, theme toggle | Frontend | 1.5 | 16 | Done | 2026-10-13 |
| F-018 | Dashboard: stats, recent tasks, getting-started checklist, build progress, roster | Frontend | 1.5 | 16.2 | Done | 2026-10-13 |
| F-019 | Tasks: table with search/filters/status tabs and kanban board view | Frontend | 1.5 | 16.3, 16.4 | Done | 2026-10-13 |
| F-020 | Task create/edit dialog with scope chips, bug-filing switch, schedule | Frontend | 1.5 | 16.5 | Done | 2026-10-13 |
| F-021 | Task detail with status change and details panel | Frontend | 1.5 | 16.6 | Done | 2026-10-13 |
| F-022 | Agents list and onboarding dialog | Frontend | 1.5 | 16.7 | Done | 2026-10-13 |
| F-023 | Agent detail: overview form, Markdown instructions editor with preview, tool permission editor, tasks tab, pause/resume | Frontend | 1.5 | 16.8–16.11 | Done | 2026-10-13 |
| F-024 | Target apps table and add/edit side sheet with encrypted test login | Frontend | 1.5 | 16.12, 16.13 | Done | 2026-10-13 |
| F-025 | Secrets vault screen | Frontend | 1.5 | 16.14 | Done | 2026-10-13 |
| F-026 | Placeholder screens for Runs, Approvals, Usage; 404 page | Frontend | 1.5 | 16.15, 16.16 | Done | 2026-10-13 |
| F-027 | `scripts/setup.sh` (Python venv, Node packages, DB, seed) and `scripts/dev.sh` (start both apps) | Tooling | 1.5 | 03 | Done | 2026-10-13 |
| F-028 | Demo Shop practice app with 6 seeded bugs (`eval-app/`), served on :4000; seeded target + task | Tooling | 2 | 13 | Done | 2026-10-13 |
| F-029 | Runtime adapter contract + registry (`app/runtime/base.py`, `registry.py`) | Backend | 2 | 07 | Done | 2026-10-13 |
| F-030 | Platform tools for agents: task context, test login (masked), test plan, results, bug drafts, file bug (GitHub), screenshots as artifacts, complete task | Backend | 2–3 | 07 | Done | 2026-10-13 |
| F-031 | Fake runtime: scripted QA agent using the real tools, incl. approval pause | Backend | 2 | 07 | Done | 2026-10-13 |
| F-032 | Worker: SKIP LOCKED claim loop, 2 concurrent runs, timeout, cancel, crash recovery, approval expiry | Backend | 2 | 08 | Done | 2026-10-13 |
| F-033 | Runs API: start, list, get, cancel, events, test cases, bugs, artifacts, artifact file | Backend | 2 | 06 | Done | 2026-10-13 |
| F-034 | Live run stream over Server-Sent Events (`GET /runs/{id}/stream`) | Backend | 2 | 06 | Done | 2026-10-13 |
| F-035 | Real QA agent: OpenAI Agents SDK on Azure OpenAI with Playwright MCP browser, run hooks, per-run budget, resume from saved state | Backend | 3 | 07, 10 | Done (needs Azure values) | 2026-10-13 |
| F-036 | Approvals: ask-first pause, approval records with bug preview, decide API, automatic resume run, rejected bugs marked | Backend | 3 | 10 | Done | 2026-10-13 |
| F-037 | Budgets: monthly budget check at start, cost ledger, usage API, runtime status API | Backend | 3 | 10 | Done | 2026-10-13 |
| F-038 | Tests: 5 run-lifecycle tests + 1 real-adapter test with scripted model and real browser (27 total) | Backend | 3 | 13 | Done | 2026-10-13 |
| F-039 | Live run page: live log, test results, bugs, screenshots, latest screenshot, stats, cancel, run again, inline approvals, auto-jump to follow-up run | Frontend | 2–3 | 12 | Done | 2026-10-13 |
| F-040 | Runs list with status tabs; "Run now" / "Watch live run" and run history on task page | Frontend | 2 | 12 | Done | 2026-10-13 |
| F-041 | Approvals inbox (pending / approved / rejected) with sidebar badge | Frontend | 3 | 12 | Done | 2026-10-13 |
| F-042 | Usage & cost page with Azure connection status; dashboard Azure banner | Frontend | 3 | 12 | Done | 2026-10-13 |
| F-043 | `scripts/dev.sh` also starts the worker and the Demo Shop | Tooling | 2 | 03 | Done | 2026-10-13 |
| F-050 | Logging: one pipeline for app + library logs, readable console, rotating JSON files (`var/logs/api.log`, `worker.log`), request line with request id, run id on worker lines, crash handler with traceback, secrets masked incl. tracebacks | Backend | 3 | 21 | Done | 2026-10-13 |
| F-051 | Agent roles as folders: `app/agents/<role>/` (definition + SKILL.md), catalog registry, seed from catalog; QA available, Sales / Marketing / Support planned | Backend | 3 | 22 | Done | 2026-10-13 |
| F-052 | Org chart backend: `org_positions` table, CRUD API with cycle check, reports move up on delete, agent-roles API, starter chart in seed | Backend | 3 | 22 | Done | 2026-10-13 |
| F-053 | Org chart screen: visual tree, department colours and filters, zoom, expand / collapse, add / edit / remove seats, holder person / agent / vacant; sidebar Organization section with departments | Frontend | 3 | 22 | Done | 2026-10-13 |
| F-054 | Target apps: extra allowed domains for the agent's browser (CDN, SSO, API hosts; `*` = no limit) | Full stack | 3 | 23 | Done | 2026-10-13 |
| F-055 | Default model switched to gpt-5-mini after a measured comparison with gpt-5-nano | Config | 3 | 23 | Done | 2026-10-13 |
| F-056 | Worker heartbeat + "No worker is running" banner in the console | Full stack | 3 | 20 | Done | 2026-10-13 |
| F-057 | Fix: follow-up run after approval gets its own turn budget and is billed only for its own tokens; failed runs keep their token usage | Backend | 3 | 24 | Done | 2026-10-13 |
| F-058 | Step-by-step run logs: model_call / model_reply (tokens, ms, cost) / tool_start / tool_done (ms, result) / screenshot_saved, plus queue, approval and finish summaries | Backend | 3 | 21 | Done | 2026-10-13 |
| F-059 | Runs record runtime + model; analytics API (per day, agent, model, outcomes, tests, bugs); org-wide bugs API | Backend | 3 | 16 | Done | 2026-10-13 |
| F-060 | Usage & analytics dashboard: KPIs, cost/runs per day, outcome and test donuts, bugs by severity, cost and tokens by model, model comparison, per-agent budgets; filters by agent and period | Frontend | 3 | 16 | Done | 2026-10-13 |
| F-061 | "i" info buttons on every main screen and on key cards / fields | Frontend | 3 | 16 | Done | 2026-10-13 |
| F-062 | Bugs page (all bugs, filters) and bug actions: Email developer, Raise Jira ticket, Send to manager (placeholders, "coming soon") | Frontend | 3 | 16 | Done (actions pending) | 2026-10-13 |
| F-063 | oneclarity.ai target + smoke-test task set up (production read-only rules) | Config | 3 | 25 | Done | 2026-10-13 |
| F-064 | Context trimming: older large tool outputs (page snapshots) shortened before each model call; last 6 kept in full | Backend | 3 | 26 | Done | 2026-10-13 |
| F-065 | Run page: live turns (x / max), tokens and cost (x / budget) while running | Frontend | 3 | 16 | Done | 2026-10-13 |
| F-066 | Cost: reasoning effort `low` + verbosity `low` for gpt-5 models (settings), cached-token pricing in cost estimates, `tokens_cached` in logs, retries on HTTP 429 | Backend | 3 | 27 | Done | 2026-10-14 |
| F-067 | Cost: only 15 needed browser tools offered, actions return no snapshot (`--snapshot-mode none`), trimming keeps last 4 outputs (setting), stay-in-scope and fewer-screenshots rules | Backend | 3 | 27 | Done | 2026-10-14 |
| F-068 | Run options: test chosen pages only (per run), per-run max turns and budget; `POST /tasks/{id}/runs` body | Full stack | 3 | 25 | Done | 2026-10-14 |
| F-069 | Parallel runs backend: orchestrator plan (rule-based split into sub-tasks / sub-agent runs), per-run `max_parallel` cap in the queue, merge with duplicate-bug detection, final report (+ `final-report.md`, executive summary), cancel cascade, recovery after worker restart | Backend | 3 | 26 | Done | 2026-10-14 |
| F-070 | Parallel runs UI: Run with options dialog (pages, one agent / parallel, agents at once, pages per agent, limits, split preview, worst-case cost), sub-agent lanes with live activity, final report, duplicate badges, sub-task links; Runs list hides sub-agent runs | Frontend | 3 | 26 | Done | 2026-10-14 |
| F-071 | Parallel final report shows full text (no cut-off notes); log line for the merge is a short verdict | Backend | 3 | 26 | Done | 2026-10-14 |
| F-072 | No case stays "Pending": `complete_task` asks once for missing results, leftover cases become "Skipped · Not run: reason"; sub-agents plan only cases for their own pages | Backend | 3 | 25 | Done | 2026-10-14 |
| F-073 | "Edit scope" on the task page + explanation of who decides scope vs test cases | Frontend | 3 | 25 | Done | 2026-10-14 |
| F-074 | Animated, interactive org chart: React Flow + dagre auto layout + Motion (staggered entrance, hover lift, pulsing AI seats, animated links), pan / zoom / fit, department focus | Frontend | 3 | 22 | Done | 2026-10-14 |
| F-075 | Dashboard for end users: removed getting-started and build-progress cards; period filter; runs / bugs / cost for the period; recent runs; latest bugs | Frontend | 3 | 16 | Done | 2026-10-14 |
| F-076 | Date-wise views: shared period filter (presets + custom range) and day grouping on Runs, Bugs, Approvals; period on Usage & analytics; `since` / `until` on `/runs`, `/bugs`, `/approvals`, `/analytics` | Full stack | 3 | 16 | Done | 2026-10-14 |
| F-077 | Agent onboarding: "Generate with AI" job description (mission, responsibilities, day-to-day, KPIs, access, boundaries, reporting, definition of done), editable with write / preview; also on the agent page | Full stack | 3 | 22 | Done | 2026-10-14 |
| F-078 | Parallel runs show total cost / tokens of all sub-agents in lists; parallel run keeps its start time across plan and merge; cancelled runs keep their cost; cost of 2 older runs back-filled from their usage events | Full stack | 3 | 26 | Done | 2026-10-14 |
| F-049 | Real-agent reliability: stricter browser rules, tool use forced every turn, run ends at `complete_task`, unfinished runs marked failed | Backend | 3 | 07 | Done | 2026-10-13 |

## Next numbers (planned)

| # | Feature | Milestone | Plan ref |
| --- | --- | --- | --- |
| F-044 | Scheduled runs from `schedule_cron` | 5 | 08 |
| F-045 | Jira integration for bug filing | Next | 15 |
| F-046 | Run triggers from GitHub PR / deploy webhooks | Next | 15 |
| F-047 | Langfuse / OpenTelemetry tracing of agent runs | Next | 14 |
| F-048 | Eval script that scores a run against `eval-app/BUGS.md` | 5 | 13 |
| F-079 – F-098 | See the roadmap: email / manager actions, saved suites, notifications, export, users and roles, deploy, connectors, second agent, manager agents | M5–M8 | 28 |
