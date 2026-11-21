"""Shared skill library and private per-Prism setup, without changing existing permissions.

Revision ID: 20261121_0047
Revises: 20261121_0046
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261121_0047"
down_revision = "20261121_0046"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "prism_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(360), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("required_tools", postgresql.JSONB(), nullable=False),
        sa.Column("required_connections", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "prism_skill_assignments",
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prism_skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "prism_skill_setups",
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("suggestions", postgresql.JSONB(), nullable=False),
        sa.Column("generation_note", sa.String(200), nullable=False, server_default=""),
        *timestamps(),
    )


def downgrade() -> None:
    op.drop_table("prism_skill_setups")
    op.drop_table("prism_skill_assignments")
    op.drop_table("prism_skills")
