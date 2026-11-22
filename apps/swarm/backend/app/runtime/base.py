"""Runtime adapter contract.

The platform never calls an agent framework directly. The worker builds a RunContext and
hands it to the adapter registered for the agent's `runtime` value.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.runtime.tools import PlatformTools


@dataclass
class AgentSpec:
    id: str
    key: str
    name: str
    instructions: str
    model: str
    tool_grants: dict[str, str]
    max_turns: int
    run_budget_usd: float


@dataclass
class TaskSpec:
    id: str
    title: str
    goal: str
    scope: dict[str, Any]
    target_name: str | None
    target_url: str | None
    target_environment: str | None
    target_notes: str | None
    has_test_login: bool
    extra_origins: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """A human decision on one paused tool call, used when resuming a run."""

    call_id: str
    approved: bool
    comment: str = ""
    payload: dict[str, Any] = field(default_factory=dict)  # e.g. {"answer": "..."} for ask_manager


@dataclass
class RunContext:
    run_id: str
    agent: AgentSpec
    task: TaskSpec
    work_dir: Path
    tools: PlatformTools
    emit: Callable[[str, dict[str, Any]], Awaitable[None]]
    is_cancelled: Callable[[], Awaitable[bool]]
    mark_tool_started: Callable[[str, bool], Awaitable[None]] | None = None
    checkpoint: Callable[[dict, dict[str, Any]], Awaitable[None]] | None = None
    saved_state: dict | None = None
    decisions: list[Decision] = field(default_factory=list)
    computer_key: str | None = None  # set when this run uses a Docker computer

    def grant(self, tool: str) -> str:
        return self.agent.tool_grants.get(tool, "off")


@dataclass
class Interruption:
    """A tool call that is waiting for human approval."""

    call_id: str
    tool: str
    arguments: dict[str, Any]


@dataclass
class RunResult:
    status: str  # succeeded | failed | cancelled | waiting_approval
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    summary: str = ""
    error: str | None = None
    saved_state: dict | None = None
    interruptions: list[Interruption] = field(default_factory=list)


class RuntimeAdapter(Protocol):
    type: str

    async def execute(self, ctx: RunContext) -> RunResult: ...

    def check_ready(self) -> str | None:
        """Return a human-readable reason when the runtime cannot run, else None."""
        ...


class RunCancelled(Exception):
    pass


class BudgetExceeded(Exception):
    pass
