"""Add observation feedback, signal preferences, and per-Prism budgets.

Revision ID: 20261030_0038
Revises: 20261030_0037
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0038"
down_revision = "20261030_0037"
branch_labels = None
depends_on = None

_TS = lambda: (  # noqa: E731
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
)


def upgrade() -> None:
    op.create_table(
        "prism_observation_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["prism_observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "kind"),
    )
    op.create_index("ix_prism_observation_feedback_prism_id", "prism_observation_feedback", ["prism_id"])
    op.create_index("ix_prism_observation_feedback_observation_id", "prism_observation_feedback", ["observation_id"])
    op.create_table(
        "prism_signal_preferences",
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("suppressed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        *_TS(),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prism_id", "signal_type"),
    )
    op.create_table(
        "prism_budgets",
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_runs_per_day", sa.Integer(), nullable=True),
        sa.Column("max_model_calls_per_day", sa.Integer(), nullable=True),
        sa.Column("max_consecutive_failures", sa.Integer(), nullable=True),
        *_TS(),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prism_id"),
    )


def downgrade() -> None:
    op.drop_table("prism_budgets")
    op.drop_table("prism_signal_preferences")
    op.drop_index("ix_prism_observation_feedback_observation_id", table_name="prism_observation_feedback")
    op.drop_index("ix_prism_observation_feedback_prism_id", table_name="prism_observation_feedback")
    op.drop_table("prism_observation_feedback")
