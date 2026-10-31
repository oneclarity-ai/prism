"""Add persisted grounded conversation reviews.

Revision ID: 20261028_0021
Revises: 20261028_0020
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0021"
down_revision = "20261028_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("summary_evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attention_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manager_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_reply", sa.Boolean(), nullable=False),
        sa.Column("proposed_reply", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
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
            name=op.f("fk_agent_conversation_reviews_job_id_agent_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_conversation_reviews")),
        sa.UniqueConstraint("job_id", name=op.f("uq_agent_conversation_reviews_job_id")),
    )


def downgrade() -> None:
    op.drop_table("agent_conversation_reviews")
