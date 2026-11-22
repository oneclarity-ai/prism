"""Add durable Prism monitoring schedules and lease-claimed runs.

Revision ID: 20261030_0032
Revises: 20261029_0031
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0032"
down_revision = "20261029_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prism_trigger_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("daily_time", sa.String(length=5), nullable=False, server_default="09:00"),
        sa.Column("missed_run_policy", sa.String(length=24), nullable=False, server_default="run_once"),
        sa.Column("continuous_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("event_coalesce_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("event_cursor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prism_id"),
    )
    op.create_table(
        "prism_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("occurrence_key", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("agreement_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_policy_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("budget", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trigger_policy_id"], ["prism_trigger_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_job_id"], ["agent_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prism_id", "occurrence_key"),
    )
    op.create_index("ix_prism_runs_prism_id", "prism_runs", ["prism_id"])
    op.create_index("ix_prism_runs_trigger_policy_id", "prism_runs", ["trigger_policy_id"])
    op.create_index("ix_prism_runs_agent_job_id", "prism_runs", ["agent_job_id"])
    op.create_index("ix_prism_runs_state", "prism_runs", ["state"])
    op.create_index("ix_prism_runs_scheduled_for", "prism_runs", ["scheduled_for"])
    op.create_index("ix_prism_runs_state_lease", "prism_runs", ["state", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_prism_runs_state_lease", table_name="prism_runs")
    op.drop_index("ix_prism_runs_scheduled_for", table_name="prism_runs")
    op.drop_index("ix_prism_runs_state", table_name="prism_runs")
    op.drop_index("ix_prism_runs_agent_job_id", table_name="prism_runs")
    op.drop_index("ix_prism_runs_trigger_policy_id", table_name="prism_runs")
    op.drop_index("ix_prism_runs_prism_id", table_name="prism_runs")
    op.drop_table("prism_runs")
    op.drop_table("prism_trigger_policies")
