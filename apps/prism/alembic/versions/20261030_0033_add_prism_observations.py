"""Add evidence-linked proactive Prism observations.

Revision ID: 20261030_0033
Revises: 20261030_0032
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0033"
down_revision = "20261030_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prism_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("verified_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("inference", sa.Text(), nullable=True),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("suggested_next_step", sa.Text(), nullable=False),
        sa.Column("unknowns", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_event_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_external_id", sa.String(length=512), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["prism_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prism_id", "fingerprint"),
    )
    op.create_index("ix_prism_observations_prism_id", "prism_observations", ["prism_id"])
    op.create_index("ix_prism_observations_run_id", "prism_observations", ["run_id"])
    op.create_index("ix_prism_observations_state", "prism_observations", ["state"])
    op.create_index("ix_prism_observations_signal_type", "prism_observations", ["signal_type"])
    op.create_index(
        "ix_prism_observations_prism_state_created",
        "prism_observations",
        ["prism_id", "state", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prism_observations_prism_state_created", table_name="prism_observations")
    op.drop_index("ix_prism_observations_signal_type", table_name="prism_observations")
    op.drop_index("ix_prism_observations_state", table_name="prism_observations")
    op.drop_index("ix_prism_observations_run_id", table_name="prism_observations")
    op.drop_index("ix_prism_observations_prism_id", table_name="prism_observations")
    op.drop_table("prism_observations")
