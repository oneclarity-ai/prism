"""Add selected Teams source snapshots and normalized evidence.

Revision ID: 20261028_0020
Revises: 20261028_0019
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0020"
down_revision = "20261028_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_jobs", sa.Column("source_kind", sa.String(length=40)))
    op.add_column("agent_jobs", sa.Column("source_external_id", sa.String(length=512)))
    op.add_column("agent_jobs", sa.Column("source_label", sa.String(length=255)))
    op.add_column(
        "agent_jobs",
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(op.f("ix_agent_jobs_source_external_id"), "agent_jobs", ["source_external_id"])
    op.create_table(
        "agent_source_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_conversation_id", sa.String(length=512), nullable=False),
        sa.Column("external_message_id", sa.String(length=512), nullable=False),
        sa.Column("sender_external_id", sa.String(length=512)),
        sa.Column("sender_display_name", sa.String(length=255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("quoted_text", sa.Text()),
        sa.Column("reply_to_external_id", sa.String(length=512)),
        sa.Column("message_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_agent_source_messages_job_id_agent_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_source_messages")),
        sa.UniqueConstraint(
            "job_id", "external_message_id", name=op.f("uq_agent_source_messages_job_id")
        ),
    )
    op.create_index(op.f("ix_agent_source_messages_job_id"), "agent_source_messages", ["job_id"])
    op.create_index(
        op.f("ix_agent_source_messages_external_conversation_id"),
        "agent_source_messages",
        ["external_conversation_id"],
    )
    op.create_index(op.f("ix_agent_source_messages_sent_at"), "agent_source_messages", ["sent_at"])


def downgrade() -> None:
    op.drop_table("agent_source_messages")
    op.drop_index(op.f("ix_agent_jobs_source_external_id"), table_name="agent_jobs")
    op.drop_column("agent_jobs", "source_metadata")
    op.drop_column("agent_jobs", "source_label")
    op.drop_column("agent_jobs", "source_external_id")
    op.drop_column("agent_jobs", "source_kind")
