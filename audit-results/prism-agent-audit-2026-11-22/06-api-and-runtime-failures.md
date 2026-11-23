# 06 API and runtime failures

Back to [executive summary](00-executive-summary.md). Context: [05 shared infrastructure](05-shared-infrastructure.md).

## Live API requests made by this audit

### Before the token (unauthenticated, read-only)

| Request | Status | Meaning |
|---|---|---|
| `GET :8000/health` | 200 `{"status":"healthy"}` | Prism up |
| `GET :8000/api/v2/prisms` | 401 `operator_auth_required` | Operator token required (`core/security.py`); expected security control |
| `GET :8000/api/v2/modes` | 401 | same |
| `GET :8000/api/v2/prisms/{code}/tools` (4 codes) | 401 | same |
| `GET :8080/health` | 404 `http_error` | route is `/api/v1/health`, not `/health` (inconsistent with Prism) |
| `GET :8080/api/v1/health` | 200 | swarm up |
| `GET :8080/openapi.json` | 200 | public |
| `GET :8080/healthz`, `/api/health` | 404 | not routes |

### After the user supplied the operator token (live phase)

| Request | Result |
|---|---|
| `GET /api/v2/prisms` | 200 |
| `GET /api/v2/work/status` | 200, engine available |
| `POST /prisms/{id}/qa/plan` x5 (research x2, sales, QA, sales follow-up/other) | 200; plans created for the right Prism |
| `POST /qa/runs/{id}/start` x4 | 200, state `running` |
| `POST /qa/approvals/{id}/decision` x6 (4 questions answered, 1 login rejected, 1 budget rejected) | 200 |
| `GET /qa/runs/{id}/files/0` (Sales CSV) | 200, 6,128 bytes |
| `GET /qa/runs/{id}/files/1` | 404 (no such file) |
| `POST /prisms/{researcher}/conversation/messages` (my mistake) | 200, created a queued Teams review job (cancelled) |
| `POST /agent/jobs/{id}/transition` with `"CANCELLED"` | 422 enum error (needs lowercase `cancelled`) |
| `POST /agent/jobs/{id}/evidence/sync` and `/review` (Chief of Staff) | 200 |
| `POST /agent/threads/{id}/chat-reply` | 200, `handled:false` for the CoS follow-up |

No 5xx was seen. The token was passed only as a per-command environment variable and is not in any file.

### Live runtime events

- All four runs started and ended normally; none hit a worker error.
- Approval pauses created new swarm runs as designed (`Paused for approval; continued in a follow-up run.`).
- Prism state lag: after rejecting the budget card the Prism run read `waiting_approval` with no pending approval for under a minute, then `cancelled`.

## Recorded runtime failures (swarm DB, read-only)

61 runs: 43 succeeded, 18 failed or cancelled.

| Failure text | Runs | Classification |
|---|---|---|
| `ComputerError: Docker is not available` | 4 (11-02, 11-05 x2, 11-19) | Environment: Docker not running then |
| `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` | 3 | Unknown; sub-exception not recorded |
| `Stopped after N turns (max turns)` (15, 25, 60 x2, 80) | 5 | Expected limit |
| `All sub-agents failed` | 1 | Unknown |
| `BadRequestError: Error code: 400 ... "The response` | 1 | Provider/API; text truncated here |
| cancelled | 4 | Manager action |

The `ExceptionGroup` failures are the largest unexplained class. The error string carries no root exception, so I cannot say whether it is a tool, MCP or runtime fault. Evidence to close: reproduce with the worker's debug logging (`worker.log` only covers 11-22 02:08 to 10:04).

## Masked tool errors

Tool results that equal `An error occurred while running the tool. Please try again.`:

| Tool | Masked results | Calls with a result |
|---|---|---|
| `sign_in` | 9 | 9 |
| `save_file` | 3 | 9 |
| `record_test_result` | 1 | 71 |
| `get_test_login` | 1 | n/a |

See [PRISM-CORE-002](05-shared-infrastructure.md#core-002). A separate, looser heuristic counted 92 tool results across all runs that look like errors (for example `### Error ... Ref eNN not found`); 72 of them are in the QA Analyst runs. Those are browser-level errors the model can read, so they are not masked.

## State-transition checks

| Boundary | Result |
|---|---|
| Prism `qa_runs` terminal state vs swarm run status (last run in chain) | 33 Prism runs, 0 mismatches, 5 legacy rows without a swarm link |
| Prism `qa_approvals` status vs swarm `approvals` status | 24 vs 24 by id, **1 mismatch** (pending vs rejected) |
| Swarm event integrity | 705 `tool_call` vs 705 `tool_result` events; 704 `usage` events |
| Retries | 0 of 61 runs with `attempt` above 1 |
| Stuck runs | none in `queued`, `running` or `waiting_approval` |

## Cost and token records

Swarm `runs.cost_usd` is a calculated rate-card value. It is not provider billing. The Prism `llm_usage` ledger holds provider-reported tokens with an **estimated** cost per call. See [07](07-model-and-cost-analysis.md).

## How these numbers were produced

Read-only SQL through `SET TRANSACTION READ ONLY` on both databases, executed by small scripts copied to `evidence/tools/` (they read the DB URL through each app's own settings at run time and print no secrets). Email-like strings were redacted in output, and approval answers, chat bodies and Teams content were never printed. Raw aggregates are in `evidence/swarm-run-metrics.csv`.
