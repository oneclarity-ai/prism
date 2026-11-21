"""Add Prism unread state, notification settings, delivery claims, and presence.

Revision ID: 20261030_0034
Revises: 20261030_0033
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0034"
down_revision = "20261030_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prism_observations", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "prism_notification_settings",
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("min_urgency", sa.String(length=16), nullable=False, server_default="high"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prism_id"),
    )
    op.create_table(
        "prism_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["prism_observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id"),
    )
    op.create_index("ix_prism_notifications_prism_id", "prism_notifications", ["prism_id"])
    op.create_index(
        "ix_prism_notifications_state_created", "prism_notifications", ["state", "created_at"]
    )
    op.create_table(
        "prism_presence",
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("client_id"),
    )


def downgrade() -> None:
    op.drop_table("prism_presence")
    op.drop_index("ix_prism_notifications_state_created", table_name="prism_notifications")
    op.drop_index("ix_prism_notifications_prism_id", table_name="prism_notifications")
    op.drop_table("prism_notifications")
    op.drop_table("prism_notification_settings")
    op.drop_column("prism_observations", "read_at")
