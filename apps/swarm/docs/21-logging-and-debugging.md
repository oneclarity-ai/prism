# 21 — Logging and Debugging

Both backend processes (API and worker) log to the terminal **and** to files. Every API request gets a request id; every worker line for a run carries its run id.

## 21.1 Where logs go

| Process | Terminal | File |
| --- | --- | --- |
| API (`uvicorn`) | readable coloured lines | `backend/var/logs/api.log` (JSON) |
| Worker | readable coloured lines | `backend/var/logs/worker.log` (JSON) |

Files rotate at 10 MB and keep 5 old copies. `var/` is git-ignored.

## 21.2 What a line looks like

```
2026-10-13 22:30:05 [info     ] request    [oneclarity] method=POST path=/api/v1/tasks/…/runs status=201 ms=41.2 request_id=5d029f99f8a1
2026-10-13 22:30:06 [info     ] run_started [oneclarity] run_id=a04ea1a7 runtime=openai_agents resume=False
2026-10-13 22:30:09 [info     ] run_event   [oneclarity] run_id=a04ea1a7 seq=12 type=tool_call detail=browser_navigate
2026-10-13 22:30:41 [error    ] request    [oneclarity] method=GET path=/api/v1/… status=500 ms=3.1 request_id=9888e328e381
2026-10-13 22:30:41 [error    ] unhandled_error [oneclarity] path=/api/v1/… request_id=9888e328e381
Traceback (most recent call last): …
```

- `request`: one line per API call. Level is `info` for 2xx/3xx, `warning` for 4xx, `error` for 5xx. Health checks are skipped.
- `unhandled_error`: any crash in the API, with the full traceback. The browser only gets "Unexpected server error. Check the API log for request id …", so you can search for that id.
- `run_started`, `run_event`, `run_finished`, `run_crashed`: the worker's view of each run. `run_event` repeats every live-log step (tool calls, results, messages).

### Step-by-step lines of an agent run (worker log)

Every line of a run carries `run_id` (first 8 characters). In order:

| Event | When | Key fields |
| --- | --- | --- |
| `run_queued` (API log) | Run now pressed | task, agent, runtime, trigger |
| `run_claimed` | Worker picks the run | waited_in_queue_s |
| `run_started` | Context built | agent, model, task, target, max_turns, run_budget_usd, resume_of, decisions |
| `resume_from_saved_state` | Follow-up run after approval | turns_already_used, tokens_already_counted |
| `agent_loop_start` | Agent begins | model, tools, browser |
| `model_call` | Before each model call | turn, items_in_context |
| `model_reply` | After each model call | turn, ms, tokens_in, tokens_cached (billed cheaper, see [27](27-cost-optimization.md)), tokens_out, next_tools, run_cost_usd, budget_usd |
| `tool_start` | Agent calls a tool | turn, tool, args (secrets masked) |
| `tool_done` | Tool finished | turn, tool, ms, result (first 300 characters) |
| `screenshot_saved` | Browser saved an image | file |
| `run_message` / `run_status` / `run_log` | Agent comment, status change | text |
| `approval_decided`, `resume_run_queued` (API log) | You approve / reject | decision, comment, still_pending |
| `run_finished` | End | status, error, tokens, cost_usd, cases_pass / fail / blocked, bugs, approvals_requested |

Parallel runs ([26](26-parallel-agents-orchestration.md)) add:

| Event | When | Key fields |
| --- | --- | --- |
| `run_queued` / `run_claimed` | As above | `kind` (single / orchestrator / child), `options` (pages, limits) |
| `parallel_planned` | Orchestrator created the sub-agents | subagents, max_parallel |
| `run_started` (sub-agent) | Sub-agent begins | `parent` (parallel run id), `pages` |
| `merge_queued` | Last sub-agent ended | — |
| `parallel_merged` | Final report written | status, cases, cases_fail, bugs_unique, bugs_duplicate, subagent_cost_usd, merge_cost_usd |
| `orchestrator_crashed` | Plan or merge failed | phase, error |

Sub-agents run at the same time, so their lines interleave. Filter by `run_id`.

Example (one turn):

```
22:59:56 [info ] model_call   run_id=c783258c turn=5 items_in_context=9
22:59:56 [info ] model_reply  run_id=c783258c turn=5 ms=1840 tokens_in=9120 tokens_out=210 next_tools=record_test_result run_cost_usd=0.0231 budget_usd=3.0
22:59:56 [info ] tool_start   run_id=c783258c turn=5 tool=record_test_result args='{"case": "Wrong password is rejected", "status": "fail", …}'
22:59:56 [info ] tool_done    run_id=c783258c turn=5 tool=record_test_result ms=5 result="Recorded 'Wrong password is rejected' as fail."
```

Set `LOG_LEVEL=DEBUG` to also log every raw run event.

## 21.3 Settings (`backend/.env`)

| Setting | Default | Use |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG` for more detail, `WARNING` for less |
| `LOG_JSON` | `false` locally | `true` makes the terminal print JSON (for servers / log tools) |
| `LOG_DIR` | `./var/logs` | Folder for the log files; empty disables files |
| `LOG_SQL` | `false` | `true` prints every SQL statement (very noisy, for DB issues only) |

Restart the API and worker after changing these.

## 21.4 Everyday debugging recipes

```bash
cd backend
tail -f var/logs/api.log                     # follow the API
tail -f var/logs/worker.log                  # follow the agent runs
grep 9888e328e381 var/logs/api.log           # everything for one request id (shown in the UI error)
grep '"run_id": "a04ea1a7"' var/logs/worker.log   # everything for one run (first 8 characters of the run id)
grep '"level": "error"' var/logs/*.log       # all errors
```

With `jq` (`brew install jq`) for readable JSON:

```bash
tail -f var/logs/worker.log | jq -r '"\(.timestamp) \(.level) \(.event) \(.detail // .error // "")"'
```

## 21.5 Safety

Passwords, tokens, API keys and `Authorization` headers are masked as `***` before a line is written, including inside exception tracebacks (tested in `tests/test_health_auth.py`). Test-login passwords are also masked in run events.

## 21.6 Code

- Setup: `backend/app/core/logging.py` (one pipeline for our logs and for uvicorn / SQLAlchemy / OpenAI library logs).
- Request lines and request ids: middleware in `backend/app/main.py`.
- Crash handler: `backend/app/core/errors.py`.
- Run ids on worker lines: `backend/app/worker/executor.py`.
