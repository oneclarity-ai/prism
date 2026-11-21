# OneClarity QA Agent — Build Plan

This folder is the step-by-step plan for building the first OneClarity agent: a **QA Tester Agent**. It is also the first slice of the OneClarity agent platform, so the backend is shaped to host Sales, Marketing and other agents later.

- **Backend:** Python 3.12 + FastAPI
- **Frontend:** React + TypeScript (Vite)
- **Agent runtime:** OpenAI Agents SDK (Python) on **Azure OpenAI**, behind an adapter interface, so other runtimes (e.g. Claude Agent SDK) can be added later without changing the platform
- **Browser automation:** Playwright (through the Playwright MCP server and generated Playwright test scripts)
- **Database:** PostgreSQL

## What the QA agent does (MVP)

A user registers a web app to test (URL + optional login + optional GitHub repo), then creates a QA task such as "Regression test the checkout flow on staging". The agent:

1. Reads the task and the app's context.
2. Explores the app in a real browser.
3. Writes a test plan (Given / When / Then cases).
4. Runs the cases, capturing screenshots and console/network errors.
5. Produces a report with pass/fail per case and evidence.
6. Drafts bug reports for failures; filing them in Jira/GitHub needs human approval.

Every run is tracked: live log, tokens, cost, artifacts, and approvals.

## Read in order

| # | File | What it covers |
| --- | --- | --- |
| 01 | [01-scope-and-requirements.md](01-scope-and-requirements.md) | MVP user stories, non-goals, success criteria |
| 02 | [02-architecture.md](02-architecture.md) | Components, run flow, folder structure, tech choices |
| 03 | [03-environment-setup.md](03-environment-setup.md) | Tools, accounts, keys, local services |
| 04 | [04-backend-skeleton.md](04-backend-skeleton.md) | FastAPI project, config, Docker Compose, health checks |
| 05 | [05-data-model.md](05-data-model.md) | Tables and Alembic migrations |
| 06 | [06-backend-api.md](06-backend-api.md) | REST endpoints and WebSocket events |
| 07 | [07-agent-runtime.md](07-agent-runtime.md) | Adapter interface, OpenAI Agents SDK + Azure OpenAI adapter, tools |
| 08 | [08-run-orchestration.md](08-run-orchestration.md) | Queue, worker, heartbeats, timeouts, cancel, streaming |
| 09 | [09-qa-agent-skill.md](09-qa-agent-skill.md) | QA agent instructions, test plan and report formats |
| 10 | [10-approvals-budgets-safety.md](10-approvals-budgets-safety.md) | Ask-first actions, budgets, secrets, sandboxing |
| 11 | [11-frontend-setup.md](11-frontend-setup.md) | Vite + React + TS project, API client, state, styling |
| 12 | [12-frontend-screens.md](12-frontend-screens.md) | Screens and components |
| 13 | [13-testing-and-evals.md](13-testing-and-evals.md) | Unit/API tests, golden eval app with seeded bugs |
| 14 | [14-deployment.md](14-deployment.md) | Docker images, environments, CI |
| 15 | [15-milestones-checklist.md](15-milestones-checklist.md) | Week-by-week build order with checkboxes |
| 16 | [16-console-ui.md](16-console-ui.md) | The built console: how to run, every screen, stack, screenshots |
| 17 | [17-feature-log.md](17-feature-log.md) | Numbered list of every feature built (F-001 …) |
| 18 | [18-postgres-queries.md](18-postgres-queries.md) | Copy-paste SQL for agents, tasks, runs, cost, health, backup |
| 19 | [19-build-journal.md](19-build-journal.md) | Step-by-step log of building runs and the live agent: problems and fixes |
| 20 | [20-live-agent-guide.md](20-live-agent-guide.md) | How to run and watch the QA agent live; switching to Azure OpenAI |
| 21 | [21-logging-and-debugging.md](21-logging-and-debugging.md) | Where logs go, what lines mean, debugging recipes |
| 22 | [22-org-chart-and-agent-roles.md](22-org-chart-and-agent-roles.md) | Org chart screen + API; one backend folder per agent role |
| 23 | [23-testing-oneclarity-ai.md](23-testing-oneclarity-ai.md) | Full process to test the real OneClarity.ai site; which model to use |
| 24 | [24-how-and-when-agents-run.md](24-how-and-when-agents-run.md) | Are runs connected, what triggers them, path to 24/7 and more departments |
| 25 | [25-setup-any-website.md](25-setup-any-website.md) | Step-by-step checklist to test any website; the oneclarity.ai setup |
| 26 | [26-parallel-agents-orchestration.md](26-parallel-agents-orchestration.md) | One agent vs parallel sub-agents: how the orchestrator splits, runs and merges; options, limits, data model |
| 27 | [27-cost-optimization.md](27-cost-optimization.md) | What history the model sees, measured token use, every cost control and its setting |
| 28 | [28-roadmap.md](28-roadmap.md) | What to build next: milestones M5–M9, features, order, decisions needed |
| 29 | [29-developer-setup.md](29-developer-setup.md) | **Start here as a developer**: prerequisites, backend and frontend setup, `.env`, daily workflow, migrations, working together, troubleshooting |

## Key decisions (change here if needed)

| Decision | Choice | Why |
| --- | --- | --- |
| Agent runtime | OpenAI Agents SDK (Python) | Agent loop, function tools, MCP, human-in-the-loop approvals with resumable run state |
| LLM provider | Azure OpenAI (team choice) | Chosen by OneClarity; models are Azure **deployments** configured per agent |
| Second runtime | Claude Agent SDK adapter, later and optional | Proves the adapter contract; not needed for the MVP |
| Default model | A GPT-class Azure deployment for runs; a smaller/cheaper deployment for summaries | Set via `AZURE_OPENAI_DEPLOYMENT`; configurable per agent |
| Job execution | Postgres-backed queue + Python worker process | No extra infra for the MVP; can move to Temporal later |
| Browser | Playwright MCP server in a sandbox container | The agent drives a real browser; evidence is real screenshots |
| Frontend kit | shadcn/ui + Tailwind v4, lucide icons, Geist font, npm | Rich, accessible components we own as source |
| Reuse from Paperclip | `qa-acceptance` skill, QA persona, task/run/approval data model ideas | MIT licensed; proven patterns |
