from pathlib import Path

from app.agents.base import AgentDefinition

# Planned: needs a helpdesk connector (Zendesk / Freshdesk) before it can run.
DEFINITION = AgentDefinition(
    key="support-agent",
    name="Customer Support Agent",
    role="support",
    department="Customer Success",
    description="Triages tickets, drafts replies from the knowledge base and escalates to humans.",
    folder=Path(__file__).parent,
    status="planned",
    tool_grants={
        "get_task_context": "allowed",
        "add_comment": "allowed",
        "complete_task": "allowed",
        "send_reply": "ask_first",
    },
)
