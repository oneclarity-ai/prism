"""Add v2.1 preferences and feedback provenance.

Revision ID: 20261028_0023
Revises: 20261028_0022
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0023"
down_revision = "20261028_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_conversation_reviews",
        sa.Column(
            "applied_preference_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "agent_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("source_kind", sa.String(length=60), nullable=False),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["source_thread_id"], ["agent_threads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_preferences_scope", "agent_preferences", ["scope"])
    op.create_index(
        "ix_agent_preferences_source_thread_id", "agent_preferences", ["source_thread_id"]
    )
    op.create_index("ix_agent_preferences_is_active", "agent_preferences", ["is_active"])
    op.create_index("ix_agent_preferences_expires_at", "agent_preferences", ["expires_at"])
    op.create_table(
        "agent_feedback_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["execution_id"], ["tool_executions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("job_id", "proposal_id", "execution_id", "event_type"):
        op.create_index(f"ix_agent_feedback_events_{column}", "agent_feedback_events", [column])


def downgrade() -> None:
    op.drop_table("agent_feedback_events")
    op.drop_table("agent_preferences")
    op.drop_column("agent_conversation_reviews", "applied_preference_ids")
