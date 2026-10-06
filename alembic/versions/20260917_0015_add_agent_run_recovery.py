"""add bounded agent run recovery

Revision ID: 20260917_0015
Revises: 20260917_0014
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_0015"
down_revision = "20260917_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("agent_runs", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_last_attempt_at", "agent_runs", ["last_attempt_at"])
    op.create_index("ix_agent_runs_next_retry_at", "agent_runs", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_next_retry_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_last_attempt_at", table_name="agent_runs")
    op.drop_column("agent_runs", "next_retry_at")
    op.drop_column("agent_runs", "last_attempt_at")
    op.drop_column("agent_runs", "attempt_count")
