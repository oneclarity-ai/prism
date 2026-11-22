from pathlib import Path

from app.agents.base import AgentDefinition

DEFINITION = AgentDefinition(
    key="qa-agent",
    name="QA Agent",
    role="qa",
    department="Technology",
    description="Tests web apps in a real browser and reports bugs with evidence.",
    folder=Path(__file__).parent,
    status="available",
    max_turns=150,  # a full regression needs many browser steps; the per-run budget still caps cost
    tool_grants={
        "get_task_context": "allowed",
        "get_test_login": "allowed",
        "save_test_plan": "allowed",
        "record_test_result": "allowed",
        "draft_bug": "allowed",
        "add_comment": "allowed",
        "complete_task": "allowed",
        "file_bug": "ask_first",
        "browser": "allowed",
    },
)
