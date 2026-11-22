from pathlib import Path

from app.agents.base import AgentDefinition

# Planned: needs CRM + email connectors (HubSpot / Salesforce, Gmail) before it can run.
DEFINITION = AgentDefinition(
    key="sales-sdr-agent",
    name="Sales SDR Agent",
    role="sales",
    department="Sales",
    description="Researches leads, drafts personalised outreach and books meetings.",
    folder=Path(__file__).parent,
    status="planned",
    tool_grants={
        "get_task_context": "allowed",
        "add_comment": "allowed",
        "complete_task": "allowed",
        "send_email": "ask_first",
    },
)
