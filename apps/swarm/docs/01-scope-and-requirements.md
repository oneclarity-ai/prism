# 01 — Scope and Requirements

## Goal

Ship a QA agent that can test a real web app end to end and hand back a trustworthy report, inside a small platform that tracks every run.

## Users

- **QA lead / engineer:** creates test tasks, reviews reports, approves bug filing.
- **Admin:** configures agents, models, budgets, integrations.

## MVP user stories

1. As an admin, I can create the QA agent with a name, instructions, model and monthly budget.
2. As a user, I can register a **target app**: name, base URL, environment (staging/prod), optional test login (stored as a secret), optional GitHub repo.
3. As a user, I can create a **QA task** for a target app with a goal ("Test login and password reset") and an optional scope (URLs, features, acceptance criteria).
4. As a user, I can start the task now or schedule it (e.g. nightly).
5. As a user, I see the run **live**: agent steps, tool calls, screenshots, status.
6. When the run finishes, I get a **report**: test plan, pass/fail per case, evidence, summary, tokens and cost.
7. For each failure, the agent drafts a **bug report** (title, steps, expected, actual, severity, evidence).
8. Filing a bug to GitHub Issues or Jira is **ask-first**: I approve or reject in an Approvals inbox, then the agent continues.
9. I can cancel a running task and re-run a finished one.
10. The agent stops when it hits its per-run or monthly budget.

## Non-goals for the MVP

- Multi-tenant SaaS, SSO, RBAC (single organisation; simple login is enough).
- Mobile app testing, load testing, security scanning.
- Self-healing test maintenance across releases.
- Other agents (Sales, Marketing) — the platform is ready for them but they are not built.

## Success criteria

| Measure | Target for MVP |
| --- | --- |
| Seeded bugs found on the eval app (see 13) | at least 7 of 10 |
| False bug reports per run | at most 1 |
| Run completes without manual help | 9 of 10 runs |
| Median run time for a 5-page flow | under 10 minutes |
| Cost per run (5-page flow) | under a configurable limit, e.g. USD 2 |
| Every failure has screenshot evidence | 100% |

## Constraints

- The agent must never use production credentials unless explicitly configured.
- All external writes (bug filing, comments on PRs) go through approvals in the MVP.
- Every run must be auditable: who started it, what the agent did, what it cost.
