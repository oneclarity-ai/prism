"""Add persisted Agent Chat messages.

Revision ID: 20261028_0022
Revises: 20261028_0021
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0022"
down_revision = "20261028_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_thread_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["agent_threads.id"],
            ondelete="CASCADE",
            name=op.f("fk_agent_thread_messages_thread_id_agent_threads"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_jobs.id"],
            ondelete="SET NULL",
            name=op.f("fk_agent_thread_messages_job_id_agent_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_thread_messages")),
    )
    op.create_index(
        op.f("ix_agent_thread_messages_thread_id"), "agent_thread_messages", ["thread_id"]
    )
    op.create_index(op.f("ix_agent_thread_messages_job_id"), "agent_thread_messages", ["job_id"])


def downgrade() -> None:
    op.drop_table("agent_thread_messages")
