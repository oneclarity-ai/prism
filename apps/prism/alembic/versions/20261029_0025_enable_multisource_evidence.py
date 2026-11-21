"""Allow the same Graph message identifier in different job sources.

Revision ID: 20261029_0025
Revises: 20261029_0024
Create Date: 2026-10-29
"""

from alembic import op

revision = "20261029_0025"
down_revision = "20261029_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_agent_source_messages_job_id", "agent_source_messages", type_="unique")
    op.create_unique_constraint(
        "uq_agent_source_messages_job_conversation_message",
        "agent_source_messages",
        ["job_id", "external_conversation_id", "external_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_agent_source_messages_job_conversation_message",
        "agent_source_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_source_messages_job_id",
        "agent_source_messages",
        ["job_id", "external_message_id"],
    )
