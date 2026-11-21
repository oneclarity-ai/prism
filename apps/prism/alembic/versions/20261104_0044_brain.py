"""Shared brain: what every Prism knows about the organisation.

Revision ID: 20261104_0044
Revises: 20261103_0043
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261104_0044"
down_revision = "20261103_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brain_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="approved"),
        sa.Column("source", sa.String(8), nullable=False, server_default="user"),
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_brain_entries_status", "brain_entries", ["status"])
    op.create_index("ix_brain_entries_prism_id", "brain_entries", ["prism_id"])


def downgrade() -> None:
    op.drop_table("brain_entries")
