"""add response policy version for deployment-aware recovery

Revision ID: 20260918_0016
Revises: 20260917_0015
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260918_0016"
down_revision = "20260917_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("policy_version", sa.String(length=64), nullable=True))
    op.create_index("ix_agent_runs_policy_version", "agent_runs", ["policy_version"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_policy_version", table_name="agent_runs")
    op.drop_column("agent_runs", "policy_version")
