# 07 — Agent Runtime

## 1. Adapter interface (`app/runtime/base.py`)

The platform never calls an agent framework directly. It calls an adapter.

```python
from dataclasses import dataclass
from typing import Protocol, Callable, Awaitable

@dataclass
class RunContext:
    run_id: str
    agent: "AgentConfig"        # name, instructions, model, tool_grants, budgets
    task: "TaskView"            # title, goal, scope, target app (no secret values)
    prompt: str                 # built by the platform for this run
    session_id: str | None      # resume a previous session if set
    emit: Callable[[str, dict], Awaitable[None]]      # write a run_event
    should_cancel: Callable[[], bool]

@dataclass
class RunResult:
    status: str                 # succeeded | failed | cancelled | timed_out
    session_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None

class RuntimeAdapter(Protocol):
    type: str
    async def execute(self, ctx: RunContext) -> RunResult: ...
    async def test_environment(self) -> dict: ...
```

A registry maps `agents.runtime` → adapter instance. Adding the OpenAI Agents SDK later = one new file implementing this protocol.

## 2. OpenAI Agents SDK adapter on Azure OpenAI (`app/runtime/openai_agents.py`)

Responsibilities:

1. Build an Azure client once per worker: `AsyncAzureOpenAI(azure_endpoint=..., api_key=..., api_version=...)`, wrapped in `OpenAIChatCompletionsModel(model=<deployment name>, openai_client=client)`. Disable OpenAI-hosted tracing (`set_tracing_disabled(True)`) because traces should not leave Azure; use our own `run_events` (and Langfuse later).
2. Build the SDK `Agent` from the agent row: instructions (QA skill + agent instructions), model (Azure deployment from `agents.model`), platform function tools, MCP servers.
3. Register **MCP servers**: `playwright` — the Playwright MCP server (`MCPServerStdio` in dev; `MCPServerStreamableHttp` to the sandbox container later).
4. Platform tools are SDK **function tools**; risky ones (`file_bug`) are created with `needs_approval=True` (see 10).
5. Run with `Runner.run_streamed(agent, input, max_turns=...)`; convert each stream event to a `run_event` (`message`, `tool_call`, `tool_result`).
6. Check `ctx.should_cancel()` between events; cancel the stream on request.
7. If the result has **interruptions** (approval needed): save `result.to_state()` on the run, create approval rows, end the run as `waiting_approval`. After the decision, a resume run loads the state, calls `state.approve(...)` / `state.reject(...)` and runs again with `Runner.run(agent, state)`.
8. Sum token usage from the result; compute cost from a per-deployment price table in settings; return `RunResult`.

Hosted tools (web search, file search, code interpreter) are OpenAI-platform features and may not be available on Azure through Chat Completions; do not depend on them. Check the current SDK docs for exact names before coding and pin the `openai-agents` version.

## 3. Platform tools (`app/tools/`)

These are the only way the agent changes OneClarity state. Each validates input with Pydantic and writes to the DB.

| Tool | Input | Effect | Permission |
| --- | --- | --- | --- |
| `get_task_context` | — | Returns task goal, scope, target app URL, previous run summary | allowed |
| `get_test_login` | — | Returns test username/password for the target app | allowed, only for that target, value redacted from logs |
| `save_test_plan` | list of cases (title, given, when, then) | Inserts `test_cases` (status pending) | allowed |
| `record_test_result` | case id, status, notes, screenshot path | Updates case, links artifact | allowed |
| `save_artifact` | local file path, kind | Copies file to artifact storage | allowed |
| `draft_bug` | case id, title, steps, expected, actual, severity | Inserts `bug_drafts` | allowed |
| `file_bug` | bug draft id, destination (`github`/`jira`) | Creates issue externally | **ask first** |
| `add_comment` | text | Progress note on the task | allowed |
| `complete_task` | summary, overall status | Writes final report, ends run | allowed |

## 4. Browser tools (Playwright MCP)

Allowed: navigate, click, type, select, hover, wait, snapshot (accessibility tree), take screenshot, console messages, network requests, tabs. Blocked: file upload outside the run folder, arbitrary JavaScript evaluation unless enabled per target.

Restrict navigation to the target app's domain with an allowlist (MCP server option or a proxy in the sandbox).

## 5. Sandbox (`sandbox/`)

- Dockerfile: Node + `@playwright/mcp` + Chromium.
- Runs the MCP server over HTTP inside the Docker network; screenshots written to a mounted per-run folder.
- No cloud credentials or OneClarity secrets inside the container.

## Steps

1. Write `base.py` and the registry.
2. Write a fake adapter (`FakeAdapter`) that emits scripted events — lets you build orchestration and UI before spending tokens.
3. Write `openai_agents.py` (Azure client) with only `get_task_context`, `add_comment` and `complete_task`; run it against a simple prompt.
4. Add Playwright MCP (stdio, local) and the remaining platform tools.
5. Move Playwright MCP into the sandbox container.

## Done when

- A run against the eval app navigates pages, saves at least one screenshot artifact and a test plan, and ends with `complete_task`.
- Token usage and cost are stored on the run.
