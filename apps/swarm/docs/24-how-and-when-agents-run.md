# 24 — How and When Agents Run

## 24.1 Are runs connected to each other?

Each run is an **independent work session** (a "heartbeat"): the agent gets the task, works until it calls `complete_task` (or hits a limit), and writes a summary. Nothing keeps running between runs.

There are only two links between runs:

| Link | What carries over |
| --- | --- |
| **Resume after approval** | When a run pauses for your decision, the follow-up run continues the **same** conversation (saved state), with the same test cases and bugs. The UI shows "This run continues the paused run". |
| **Same task, next run** | The agent receives the **previous run's summary** in its task context (`previous_run_summary`), so it knows what happened last time. Test cases and bugs are not reused; each run makes its own. |
| **Parallel run → sub-agents** | A parallel run plans sub-agent runs, waits for them, then merges their test cases and bugs into one final report ([26](26-parallel-agents-orchestration.md)). Sub-agents do not talk to each other. |

So the three runs on your screenshot were independent attempts on the same task. They were also made **before** the reliability fix (F-049): back then a run that stopped early still showed "Succeeded". Runs now end as **Failed** if the agent never finishes with `complete_task`.

## 24.2 When do agents run today?

| Trigger | Status |
| --- | --- |
| **Run now** button on a task | Built |
| **Run with options**: chosen pages, one agent or parallel sub-agents | Built ([25.9](25-setup-any-website.md#259-test-one-page-or-choose-pages-per-run), [26](26-parallel-agents-orchestration.md)) |
| Follow-up run after the last approval | Built (automatic) |
| Schedule (`schedule_cron` on a task, e.g. every night at 02:00) | Field exists; scheduler **not built yet** (F-044) |
| Events: GitHub pull request, deploy finished, webhook | Not built (F-046) |
| Another agent assigns work (manager → worker) | Not built |

## 24.3 "24/7" in this design

Agents do **not** run in an endless loop (that would burn money). 24/7 means:

1. The **worker is always on** (a server or container instead of your Mac).
2. Runs start from **triggers**: schedules (nightly regression), events (every PR, every deploy), and other agents.
3. Each run is short and bounded by **budgets** (per run and per month), timeouts and max turns.
4. Risky actions still wait for a human (**approvals**), and humans see everything in the console.

This is the same "heartbeat" model Paperclip uses.

## 24.4 Path to a full organization

| Step | What it adds |
| --- | --- |
| 1. Scheduler (F-044) | Nightly / weekly runs from `schedule_cron` |
| 2. Event triggers (F-046) | Run QA on every PR or deploy |
| 3. Deploy the worker | Always-on server or container; browser in a sandbox |
| 4. Manager agents | A "Chief of Staff" or department-manager agent breaks goals into tasks and assigns them along the org chart ([22](22-org-chart-and-agent-roles.md)) |
| 5. New departments | Sales, Marketing, Support agents from `backend/app/agents/<role>/` once their tools (CRM, email, CMS, helpdesk) exist |
| 6. Goals | Company goals at the top; every task traces up to one (Paperclip's goal tree) |
