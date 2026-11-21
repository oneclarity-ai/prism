from app.core.errors import AppError
from app.runtime.base import RuntimeAdapter
from app.runtime.fake import FakeAdapter
from app.runtime.openai_agents import OpenAIAgentsAdapter

_ADAPTERS: dict[str, RuntimeAdapter] = {
    FakeAdapter.type: FakeAdapter(),
    OpenAIAgentsAdapter.type: OpenAIAgentsAdapter(),
}


def get_adapter(runtime: str) -> RuntimeAdapter:
    adapter = _ADAPTERS.get(runtime)
    if adapter is None:
        raise AppError(f"Unknown agent runtime '{runtime}'", code="unknown_runtime")
    return adapter


def available_runtimes() -> list[str]:
    return list(_ADAPTERS)


def register_adapter(adapter: RuntimeAdapter) -> None:
    """Used by tests to plug in a custom adapter."""
    _ADAPTERS[adapter.type] = adapter
