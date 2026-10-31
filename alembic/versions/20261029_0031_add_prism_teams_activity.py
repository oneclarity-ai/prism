"""Add durable Prism Teams source policies and incremental activity storage.

Revision ID: 20261029_0031
Revises: 20261029_0030
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0031"
down_revision = "20261029_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prism_teams_source_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="all_chats"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("discovery_cursor_external_id", sa.String(length=512), nullable=True),
        sa.Column("last_discovery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_discovery_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prism_id"),
    )
    op.create_table(
        "prism_teams_source_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("disposition", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("chat_type", sa.String(length=32), nullable=True),
        sa.Column(
            "participants",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["prism_teams_source_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "external_id"),
    )
    op.create_index("ix_prism_teams_source_rules_policy_id", "prism_teams_source_rules", ["policy_id"])
    op.create_table(
        "prism_teams_source_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_external_id", sa.String(length=512), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_id", sa.String(length=512), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="idle"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prism_id", "source_external_id"),
    )
    op.create_index("ix_prism_teams_source_cursors_prism_id", "prism_teams_source_cursors", ["prism_id"])
    op.create_table(
        "prism_external_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("microsoft_user_id", sa.String(length=255), nullable=False),
        sa.Column("source_external_id", sa.String(length=512), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("external_message_id", sa.String(length=512), nullable=False),
        sa.Column("event_kind", sa.String(length=24), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender_external_id", sa.String(length=512), nullable=True),
        sa.Column("sender_display_name", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("reply_to_external_id", sa.String(length=512), nullable=True),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_prism_external_events_prism_id", "prism_external_events", ["prism_id"])
    op.create_index(
        "ix_prism_external_events_prism_source_occurred",
        "prism_external_events",
        ["prism_id", "source_external_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prism_external_events_prism_source_occurred", table_name="prism_external_events")
    op.drop_index("ix_prism_external_events_prism_id", table_name="prism_external_events")
    op.drop_table("prism_external_events")
    op.drop_index("ix_prism_teams_source_cursors_prism_id", table_name="prism_teams_source_cursors")
    op.drop_table("prism_teams_source_cursors")
    op.drop_index("ix_prism_teams_source_rules_policy_id", table_name="prism_teams_source_rules")
    op.drop_table("prism_teams_source_rules")
    op.drop_table("prism_teams_source_policies")
