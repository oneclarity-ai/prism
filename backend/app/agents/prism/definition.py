from pathlib import Path

from app.agents.base import AgentDefinition

# Template only: Prism creates one agent row per Prism (key prism-<id>) with its own instructions and grants.
DEFINITION = AgentDefinition(
    key="prism-agent",
    name="Prism Agent",
    role="prism",
    department="Operations",
    description="A general agent with its own computer. Instructions and tools come from the Prism that owns it.",
    folder=Path(__file__).parent,
    status="planned",
    max_turns=120,
    tool_grants={
        "get_task_context": "allowed",
        "add_note": "allowed",
        "update_checklist": "allowed",
        "ask_manager": "ask_first",
        "complete_task": "allowed",
        "browser": "allowed",
        "computer": "allowed",
        "confirm_action": "ask_first",
    },
)
