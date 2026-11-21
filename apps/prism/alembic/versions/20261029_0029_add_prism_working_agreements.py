"""Add immutable working agreements for Prism v2.2.

Revision ID: 20261029_0029
Revises: 20261029_0028
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0029"
down_revision = "20261029_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prisms", sa.Column("agreement_revision", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_table(
        "prism_working_agreements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("template_key", sa.String(length=80), nullable=False),
        sa.Column("template_version", sa.String(length=80)),
        sa.Column("agreement", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source_answer_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["onboarding_session_id"], ["prism_onboarding_sessions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prism_working_agreements")),
        sa.UniqueConstraint("prism_id", "revision"),
    )
    op.create_index(
        "ix_prism_working_agreements_prism_id", "prism_working_agreements", ["prism_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_prism_working_agreements_prism_id", table_name="prism_working_agreements")
    op.drop_table("prism_working_agreements")
    op.drop_column("prisms", "agreement_revision")
