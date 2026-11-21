from pathlib import Path

from app.agents.base import AgentDefinition

# Planned: needs CMS, social scheduler and analytics connectors before it can run.
DEFINITION = AgentDefinition(
    key="marketing-content-agent",
    name="Marketing Content Agent",
    role="marketing",
    department="Marketing",
    description="Plans the content calendar, drafts posts and blogs, and reports on campaigns.",
    folder=Path(__file__).parent,
    status="planned",
    tool_grants={
        "get_task_context": "allowed",
        "add_comment": "allowed",
        "complete_task": "allowed",
        "publish_post": "ask_first",
    },
)
