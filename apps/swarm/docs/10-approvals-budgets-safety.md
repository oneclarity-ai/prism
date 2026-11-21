# 10 — Approvals, Budgets and Safety

## Approvals (ask-first)

Uses the OpenAI Agents SDK human-in-the-loop feature: tools marked `needs_approval` pause the run and return **interruptions** with a serialisable run state.

1. Each agent has `tool_grants`: `{ "file_bug": "ask_first", "record_test_result": "allowed", … }`. Unknown tools default to `off` and are not given to the agent at all.
2. When building tools, the adapter sets `needs_approval=True` for every `ask_first` tool.
3. When the run returns interruptions: store `result.to_state()` (JSON) on the run, insert one `approvals` row per interruption (`pending`, with the tool name and arguments), set the run to `waiting_approval`, notify the UI. The worker slot is freed; nothing waits in memory.
4. `POST /approvals/{id}/decision` stores the decision. When all approvals of the run are decided, the API enqueues a **resume run** (trigger `approval`).
5. The resume run loads the state (`RunState.from_json`), calls `state.approve(i)` or `state.reject(i)` for each interruption, then `Runner.run(agent, state)`. Rejected tools return a refusal the agent can read, together with the reviewer's comment added to the conversation.
6. Approval timeout (default 24 h): the run ends `cancelled` with reason `approval_timeout`; bug drafts stay so the user can file them later.
7. Run state is loaded only from our own database (the SDK warns that saved state is not authenticated).

## Budgets

| Limit | Where checked | Behaviour |
| --- | --- | --- |
| Per-run cost cap (e.g. USD 3) | adapter, after each message using running usage | stop run → `failed` (`budget_exceeded`) |
| Per-run max turns (e.g. 80) | SDK option | stop run |
| Per-run timeout (e.g. 30 min) | worker | `timed_out` |
| Monthly per-agent budget | enqueue time + after each run | refuse new runs; pause agent at 100%; warn at 80% |

## Secrets

- Stored encrypted in `secrets`; only `get_test_login` can read the target's login, and its value is masked in `run_events` (replace with `***`).
- `AZURE_OPENAI_API_KEY` lives only in the worker's environment.
- Redact anything that looks like a token or password from logs (regex filter in structlog).

## Prompt injection

- Page text is data. The skill tells the agent never to follow instructions found on the page under test.
- Tool permissions, not the prompt, are the real guard: the browser can only reach the allowlisted domain, and external writes need approval.

## Sandbox

- Browser runs in its own container, per-run folder, no host mounts except that folder.
- Egress limited to the target domain and the MCP port in production.

## Done when

- Calling `file_bug` creates a pending approval and the run waits; approve → issue created; reject → agent receives the comment.
- A run that exceeds its cost cap stops with `budget_exceeded`.
- No secret value appears in `run_events` or logs (test with a known fake secret).
