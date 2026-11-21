# 19 — Build Journal

A running log of how milestones 2 and 3 (runs + the live QA agent) were built: each step, what went wrong, and how it was fixed. Newest entries at the bottom. Feature numbers refer to [17-feature-log.md](17-feature-log.md).

## J-01 · 2026-10-13 · Starting point

- Goal: watch the QA agent work live from the console UI.
- Checked `backend/.env`: the four `AZURE_OPENAI_*` values are **empty**. The real agent cannot call a model until they are filled in.
- Decision: build the full pipeline anyway and make it testable two ways:
  1. **Fake runtime**: a scripted agent that uses the same tools, writes real test cases and bug drafts, and needs no model. Lets you see the whole flow today.
  2. **OpenAI Agents SDK runtime on Azure**: the real agent. Works as soon as the Azure values are set.
- Checked the browser tool: `@playwright/mcp` 0.0.83 is available through `npx`.

## J-02 · Demo Shop: something for the agent to test

- Built `eval-app/site/`: a small static shop (home + search, log in, sign up, shop with quantity total, contact) with **6 seeded bugs**. The answer key is `eval-app/BUGS.md`, kept outside the served folder so the agent cannot read it.
- Problem: the first version had `// BUG` comments in `app.js`. The agent could open that file in the browser and "find" bugs by reading comments. Fixed by stripping all hints from served code.
- Served on http://localhost:4000 (`python3 -m http.server`). Test login: `demo@shop.test` / `demo123`.

## J-03 · Browser tool check

- Started `@playwright/mcp` through the Agents SDK `MCPServerStdio` and drove the Demo Shop: 25 browser tools, navigation works, uses the Chrome already installed on this Mac.
- Finding: in this MCP version, page snapshots after navigation are written to the output folder instead of returned inline. The agent must call `browser_snapshot` to read a page. Added to the QA skill.
- Finding: `browser_take_screenshot` has required parameters that change between versions; the model reads the schema, so we do not hard-code calls.
- Safety: `browser_run_code_unsafe`, `browser_evaluate` and `browser_file_upload` will be blocked with a tool filter, and the browser limited to the target's origin with `--allowed-origins`.
- API choice: run the agent with `Runner.run` plus **run hooks** (tool start/end, model end) for live events, instead of parsing the raw token stream. Simpler, and the same hooks enforce the per-run budget.

## J-04 · Runs, worker and the fake agent

- Built the run pipeline: `app/runtime/base.py` (adapter contract), `tools.py` (platform tools), `fake.py`, `registry.py`, `app/services/runs.py`, `app/worker/executor.py` + `main.py`, and `app/api/routers/runs.py`.
- Worker claims runs with `SELECT … FOR UPDATE SKIP LOCKED`, runs up to 2 at once, enforces the timeout, and marks runs left `running` by a crash as failed on restart.
- Live updates: chose **Server-Sent Events** (`GET /runs/{id}/stream`) instead of the WebSocket in plan file 06. One-way updates are all the UI needs, SSE works through the Vite proxy with the session cookie, and it reconnects on its own. The stream polls the database every 0.6 s; good enough for a handful of viewers.
- Approvals: when the agent calls an ask-first tool, the run stops as `waiting_approval` and saves its state. When every approval of that run is decided, a **resume run** is queued automatically and continues where the first one stopped.
- Tested end to end with the fake agent on the seeded "Full regression of Demo Shop" task: 53 live events, 9 test cases (7 pass, 2 fail), 2 bug drafts, 2 approvals; approve + reject → resume run filed one bug and left the other as a draft; task ended `done`. Cancel stops a running run within ~3 s.
- Problem: my first test calls returned empty responses. Cause: **your own API server was already running on port 8000** with `--reload`, and it was mid-reload when I called it. My second server could not bind the port. No harm; once reload finished the calls worked.
- Problem: a rejected bug stayed `draft`. Fixed: rejecting a `file_bug` approval now marks the bug `rejected`.
- Added to seed: target **Demo Shop (eval app)** at http://localhost:4000 with test login, and task **Full regression of Demo Shop** with bug filing allowed.

## J-05 · Real agent adapter (OpenAI Agents SDK on Azure)

- Built `app/runtime/openai_agents.py`: Azure client (`AsyncAzureOpenAI` + `OpenAIChatCompletionsModel`), 8 platform tools as SDK function tools (only those the agent's grants allow), the Playwright MCP browser (blocked: run-code, evaluate, file upload; limited to the target's origin), run hooks for live events, per-run budget check after every model reply, cancel within ~1 s, and resume from saved state with approve / reject.
- OpenAI-hosted tracing is switched off (`set_tracing_disabled`) so run data stays in OneClarity.
- Testing without Azure keys: wrote a **scripted model** (`tests/test_openai_adapter.py`) that replaces Azure and plays a fixed QA session. Everything else is real: the SDK, our tools, a real headless Chrome opening the Demo Shop, a PNG screenshot stored as an artifact, the `file_bug` approval pause, saved state, and the resume run. Passed on the first try in 6 s.
- What this does **not** prove: how well a real Azure model follows the QA skill. That needs your Azure values; see the next steps in [20-live-agent-guide.md](20-live-agent-guide.md).
- Problem: pytest runs each test in a new event loop, but the worker code uses the app's shared database engine, whose pooled connections belong to the old loop. Fixed by disposing that engine after every test.
- `scripts/dev.sh` now also starts the **worker** and the **Demo Shop**. Without the worker, runs stay `queued` forever.
- Backend tests: 27 passing (21 earlier + 5 run lifecycle + 1 real-adapter).

## J-06 · Console screens for runs

- Built the live run page, runs list, approvals inbox, usage page, and wired "Run now" on the task page. The sidebar shows a live-runs counter and an orange approvals badge.
- Tested by driving the real console in a headless browser: Run now → live log streaming → "Needs approval" with 2 bug cards → approve one, reject one with a comment → page jumps to the follow-up run → summary, results 7 pass / 2 fail, bugs `approved` and `rejected`. Three full passes; no browser errors.
- Bug found: after approving, the page did not jump to the follow-up run when the page had been opened while the run was still running. Cause: the "jump" was only armed if the run was already waiting when the page loaded. Fixed: it now arms whenever the page sees the run reach "Needs approval".
- Seen once, not reproduced in the next two full passes: a follow-up run page stayed on "Queued" with an empty log although the run had finished. Added a safety net: the run status is also polled every 4 s while active, and the live stream re-opens if the status changes while the stream is disconnected.
- Cleaned up: deleted all test runs from your `oneclarity` database; the Demo Shop task is back to "To do". The QA agent's runtime is left on **Fake** (you had chosen it) so you can try the flow right away.

## J-07 · Where things stand

- Done: everything needed to watch the QA agent work live from the console, with approvals, budgets and cost tracking.
- Waiting on you: the four `AZURE_OPENAI_*` values. Then follow [20-live-agent-guide.md](20-live-agent-guide.md) section 20.4.
- Not done yet: the browser runs on the host (no sandbox container), scheduled runs, Jira, tracing, and an automatic score against `eval-app/BUGS.md`. Listed as F-044 to F-048 in [17-feature-log.md](17-feature-log.md).

## J-08 · First real runs on Azure OpenAI (gpt-5-nano)

- Your `.env` had endpoint, key and deployment (`gpt-5-nano`) but **no `AZURE_OPENAI_API_VERSION` line**. Tested `2025-04-01-preview` and `2024-12-01-preview`: both work. Added `2025-04-01-preview`, plus cost rates for gpt-5-nano (USD 0.05 in / 0.40 out per 1M tokens, list price; check your Azure pricing page).
- Your earlier "Run now" was still **Queued** because no worker was running. Executed it with the worker code directly.

| Run | Change before the run | Result | Time | Cost |
| --- | --- | --- | --- | --- |
| 1 | none | "succeeded", 3 cases, 0 of 6 seeded bugs found, 9 screenshots | 169 s | $0.018 |
| 2 | stricter browser rules in the agent's runtime notes | good 10-case plan, executed in the browser, but ended with a chat message instead of recording results | 242 s | $0.037 |
| 3 | tool use forced every turn; run ends only at `complete_task` | finished properly: 12-case plan, 1 pass, 1 bug drafted, outcome "blocked" | 327 s | $0.038 |

- Problem 1: the model called `browser_snapshot` with a `filename`, which writes the page to a file the model cannot read, so it was "blind" and guessed CSS selectors. Fix: runtime notes now say to call `browser_snapshot` without arguments and to use element references from it.
- Problem 2: a reasoning model can end its turn with text. The run then looked "succeeded" with no results. Fix: `tool_choice="required"` + stop at `complete_task`; a run that ends without `complete_task` is now marked **failed** with a clear message.
- Problem 3 (not fixed in code): in run 3 gpt-5-nano invented a missing "cart page (404)" and gave up on the remaining cases. Demo Shop has no cart page; the total is on `shop.html`. This is the model's limit. **Recommendation: deploy a stronger model** (gpt-5-mini, gpt-4.1 or gpt-5) and set `AZURE_OPENAI_DEPLOYMENT` (or the agent's "Azure deployment" field) to it.
- The three real runs are kept in your database so you can open them under **Runs** and replay the live log and screenshots.

## J-09 · Logs, org chart, agent role folders, model choice

- **Logs.** Before: the API printed almost nothing useful and nothing went to a file. Now: one request line per call (method, path, status, ms, request id), run id on every worker line, full traceback on crashes, files in `backend/var/logs/`.
  - Problem: a secret inside an exception message was **not** masked in the log file, because masking ran before the traceback was turned into text. Fixed by masking again after formatting; covered by a test.
  - Problem: the crash handler could not read the request id because the request middleware had already cleared it. Fixed by also storing it on the request.
  - Timestamps switched from UTC to your local time.
- **Agent roles.** Moved `app/skills/qa/SKILL.md` to `app/agents/qa/SKILL.md`; each role now has `definition.py` + `SKILL.md`; Sales, Marketing and Support exist as **planned** folders.
- **Org chart.** New table + API + screen. Found while testing: long titles were cut off and departments appeared in random order; fixed (wider cards, two-line titles, Leadership first then A–Z).
- **Real-site blocker found and fixed.** The agent's browser only allowed the target's own domain, so a real site loading a CDN or redirecting to an SSO provider would break. Added "Extra allowed domains" per target app.
- **Model comparison** on the Demo Shop: gpt-5-mini found 2 real seeded bugs in 3 min for $0.14 and paused for approval to file them; gpt-5-nano found none. Default switched to gpt-5-mini. That run (`a04ea1a7`) is waiting for your approval in the console.
- Backend tests: 31 passing (added crash-handler and 3 org-chart tests).

## J-10 · Run stuck in "Queued" after approval

- Symptom: after approving the gpt-5-mini bugs, follow-up run `30f8e2d3` stayed **Queued**; "Watch live" showed an empty log.
- Cause: **no worker process was running.** Only the API (`uvicorn`) and UI (`vite`) were started, not `./scripts/dev.sh`, so nothing picked up queued runs. The approval itself worked. The Demo Shop on :4000 was not running either.
- Fix so this is visible next time: workers now write a **heartbeat** every 5 s (table `worker_heartbeats`, migration `ab71f066d260`). `GET /runtime/status` returns `workers_online`, and the console shows a red "No worker is running" banner with the exact command on the dashboard, Runs list, task page and any queued run. Test added (32 backend tests).

## J-11 · Run failed "after 80 turns", detailed logs, analytics, oneclarity.ai

- **Why run `30f8e2d3` failed.** It was the follow-up run after your approval. The SDK's saved state carries the turn counter: the paused part had already used ~54 turns, so the follow-up hit the 80-turn limit after only 26 more. Its tokens showed 0 because failed runs dropped their usage. Fixes:
  - the follow-up run now gets its **own** turn budget (turns already used + max turns);
  - token usage is counted **per run** from a baseline, so the follow-up is not billed again for the paused part;
  - failed / stopped runs keep their tokens and cost;
  - QA agent max turns raised 80 → **150** (each browser click is a turn).
  - Covered by the real-adapter test, now run with a 7-turn limit that the old code would fail.
- **Detailed logs.** New per-step lines (`model_call`, `model_reply`, `tool_start`, `tool_done`, `screenshot_saved`…), see [21](21-logging-and-debugging.md). Problem found: token counts showed as `***` because the secret filter masked every key containing "token". Narrowed it to real secret names.
- **Analytics.** Runs now store `runtime` and `model` (migration `97784155ac2a`; your 5 earlier runs back-filled: 3 × gpt-5-nano, 2 × gpt-5-mini). New `/analytics` and `/bugs` APIs and a dashboard with Recharts.
  - Problem: after installing the chart library your running UI showed a blank page. Cause: Vite's pre-bundled dependency cache was built before `react-is` (needed by Recharts) was installed, and served a 500. Fixed by installing `react-is` and clearing `frontend/node_modules/.vite`.
  - Caveat: the 3 old gpt-5-nano runs show as "succeeded" because they ran before F-049; new runs are counted correctly.
- **oneclarity.ai.** The site is a single-page app, so it was crawled in a headless browser: 30+ pages, forms on login / signup / book-demo / contact, 16 outside domains. Created target + smoke-test task with production read-only rules and analytics domains left out. Not run yet; you start it.
- Backend tests: 33 passing.

## J-12 · First oneclarity.ai run: slow but healthy

- Run `136c4b6a` (gpt-5-mini) at the time of checking: turn 79 of 150, $0.91 of the $3 budget, 17 minutes, 2 of 20 test cases recorded (both Book-demo validation checks: pass).
- Why so few results yet: the agent visits and reads many pages before recording results, and each model call got slower as the conversation grew: 4k tokens per call at turn 1, 56k at turn 71, up to ~20 s per call.
- Fix for next runs (F-064): older large tool outputs (page snapshots) are trimmed before each model call; the last 6 stay in full. Covered by `tests/test_context_trim.py`.
- Header showed 0 tokens / $0.00 while running because run totals are written at the end. Fixed (F-065): turns, tokens and cost now update live from the stream.
- Parallel agents: designed in [26](26-parallel-agents-orchestration.md); not built yet.

## J-13 · Cost cuts, page selection, parallel agents

- **Question: is history kept?** Inside one run, yes: the Azure API is stateless, so every model call re-sends the whole conversation, including every page the agent has read. Between runs only a short previous-run summary is passed. Details in [27](27-cost-optimization.md).
- **Measured cost driver** (run `136c4b6a`, cancelled by you after ~100 turns): 67k input tokens per call on average (up to 92k) and ~1,540 output tokens per call, mostly hidden reasoning at the medium default. Output tokens cost 8× input tokens on gpt-5-mini.
- **Checked against Azure before changing anything:** `reasoning_effort` low / minimal and `verbosity` low are accepted by the `gpt-5-mini` deployment on API version 2025-04-01-preview; a repeated 2.8k-token prompt came back with 2,688 tokens cached (Azure prompt caching works automatically).
- **Checked Playwright MCP 0.0.83:** actions (navigate, click) do not inline the page; they return a link to a snapshot file the agent cannot read. `--snapshot-mode none` drops that link. 25 tools are exposed; 15 are offered now.
- **Cost changes** (F-066, F-067): low reasoning and verbosity, cached-token pricing, fewer tools, trimming keeps 4 outputs, stay-in-scope rules, fewer screenshots, results recorded right after each case.
- **Parallel agents built** (F-069, F-070) as designed in [26](26-parallel-agents-orchestration.md), plus per-run page choice (F-068).
  - Problem: a parallel run's live log is written by the orchestrator and by every sub-agent at once, and event sequence numbers must be unique per run. Fixed with `append_event`, which locks the run row before taking the next number.
  - Problem: the orchestrator must not hold a worker slot while sub-agents run (with 2 slots it would block itself). Fixed by splitting it into two short runs of the same row: plan, then `waiting_children`, then the last sub-agent re-queues it for the merge.
  - Problem: the live stream closed when a run left `queued` / `running`. It now stays open during `waiting_children`.
  - Editing a sub-task in the task dialog would have erased its `focus`; the dialog now keeps it.
- **Live check** (Demo Shop, 3 sub-agents at once, gpt-5-mini, run `a559f466`): ~2 s per model call (was 7–23 s), ~13 output tokens per step (was ~1,540), ~90% of input cached. 28 test cases, 3 real bugs, **$0.05 total**, ~4 min. Details in [26](26-parallel-agents-orchestration.md).
  - Two sub-agents hit the 40-turn cap set for the test: the agent clicked each form field before typing. Added a "one `browser_fill_form` per form" rule; sub-agent default turns 60 → 80 (a turn now costs ~$0.0004).
  - The `/shop.html` sub-agent also tested login (out of its scope), and its bug "[Auth] Wrong password allows login" was not merged with sub-agent 1's "[Auth] Successful login accepted with wrong password". Duplicate rule changed from word overlap of both titles (Jaccard 0.6) to ≥ 3 shared words covering 75% of the shorter title; this pair is now a test case.
  - Lane text showed "status: failed" next to the error; now shows the error, the summary, or "Waiting for your approval". The parent log says "resumed after approval" for a follow-up sub-agent run.
- `MAX_CONCURRENT_RUNS` default raised 2 → 4.
- Backend tests: 41 passing (new `tests/test_parallel.py`, cost tests in `tests/test_context_trim.py`). Frontend builds.

## J-14 · Report cut-off, pending cases, date filters, animated org chart, AI job descriptions

Feedback from the first parallel oneclarity.ai run (`a2246800`, only `/status` selected, $0.05):

- **Final report cut off** ("…indicating auth refresh endpo"). Cause: the merge shortened each sub-agent's notes to 600 characters and failed-case notes to 160. Removed both limits. The run's status line in the live log now shows a short verdict instead of the first 2,000 characters of the report.
- **3 of 8 cases stayed "Pending".** The `/status` sub-agent received the task's shared acceptance criteria (Book demo / Contact / Sign up forms) and planned cases for them, then finished without running them (they belong to other pages). Fixes (F-072):
  - the end of the run is now decided by a custom `tool_use_behavior`: `complete_task` refuses once while cases have no result, and the run continues so the agent can record them (the SDK's `StopAtTools` would have ended the run on the first call);
  - leftover cases are marked **Skipped** with "Not run: …" when a run ends;
  - instructions: plan only cases you will run on your pages; every planned case needs a result.
- **Parallel runs showed $0.00, 0 tokens and "5s"** in Runs and on the dashboard: those columns showed only the orchestrator's own merge cost, and its start time was reset when the worker picked it up again for the merge. Now lists show the total of all sub-agents (`total_cost_usd`, `total_tokens`) and the start time is kept.
- **Cancelled runs lost their cost.** The cancel path returned no usage. Fixed; the cancelled oneclarity.ai run `136c4b6a` ($1.37, 4.55M tokens) and the old failed run `30f8e2d3` ($0.28) were back-filled from their last usage event, including the budget ledger.
- **Dashboard** cleaned for end users (F-075) and every list got a period filter with day grouping (F-076). Problem found: "Last 7 days" by `days=7` spans 8 calendar days; analytics keeps `days` for the old behaviour and uses `since` / `until` from the browser for exact local days.
- **Org chart** rebuilt on React Flow + dagre + Motion (F-074). Problem: the minimap covered the bottom row of cards on a laptop screen and rendered empty in the first frame; removed it (zoom controls and fit-view remain).
- **AI job description** for new agents (F-077): one Azure call, ~4,600 characters, $0.002, verified in the browser.
- Backend tests: 45 passing. Frontend builds.

## J-15 · Developer handover

- Wrote [29-developer-setup.md](29-developer-setup.md) (prerequisites, backend and frontend setup, `.env` reference, daily workflow, migrations, working together, troubleshooting) and a root `README.md`.
- Found while writing it:
  - `backend/.env.example` was missing the settings added since milestone 3 (prices, cost controls, worker limits). It now lists every setting, with the defaults `2025-04-01-preview` / `gpt-5-mini`.
  - `scripts/setup.sh` did not create the test database `oneclarity_test`, so `pytest` failed on a fresh machine. It does now, and checks for `python3`.
  - The project folder was not a Git repository and had no root `.gitignore` (only `backend/` and `frontend/` had one). Added a root `.gitignore` that keeps out `.env`, `backend/var`, virtual envs and `node_modules`; the Git steps are in 29.2.
  - The Docker worker image has no Node.js or Chrome, so real browser runs only work with a local worker. Noted in 29.5; fixing it is part of M6.
