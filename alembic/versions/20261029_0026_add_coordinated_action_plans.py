"""Add coordinated action plans and proposal dependencies.

Revision ID: 20261029_0026
Revises: 20261029_0025
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0026"
down_revision = "20261029_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_action_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column(
            "plan_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_agent_action_plans_state", "agent_action_plans", ["state"])
    op.add_column(
        "action_proposals",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("sequence", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "action_proposals",
        sa.Column(
            "depends_on_logical_action_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_action_proposals_plan_id_agent_action_plans",
        "action_proposals",
        "agent_action_plans",
        ["plan_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_action_proposals_plan_id", "action_proposals", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_action_proposals_plan_id", table_name="action_proposals")
    op.drop_constraint(
        "fk_action_proposals_plan_id_agent_action_plans",
        "action_proposals",
        type_="foreignkey",
    )
    op.drop_column("action_proposals", "depends_on_logical_action_ids")
    op.drop_column("action_proposals", "sequence")
    op.drop_column("action_proposals", "plan_id")
    op.drop_index("ix_agent_action_plans_state", table_name="agent_action_plans")
    op.drop_table("agent_action_plans")
