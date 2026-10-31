"""Add durable, server-owned Prism v2.2 onboarding state.

Revision ID: 20261029_0028
Revises: 20261029_0027
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0028"
down_revision = "20261029_0027"
branch_labels = None
depends_on = None

onboarding_status = postgresql.ENUM(
    "IN_PROGRESS", "COMPLETED", "CANCELLED", name="prism_onboarding_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    onboarding_status.create(bind, checkfirst=True)
    op.create_table(
        "prism_onboarding_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", onboarding_status, server_default="IN_PROGRESS", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "question_set_version",
            sa.String(length=80),
            server_default="fallback-v1",
            nullable=False,
        ),
        sa.Column("generation_note", sa.String(length=160)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prism_onboarding_sessions")),
        sa.UniqueConstraint("prism_id"),
    )
    op.create_table(
        "prism_onboarding_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text()),
        sa.Column("question_type", sa.String(length=40), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("allows_custom", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "choices", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["prism_onboarding_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prism_onboarding_questions")),
        sa.UniqueConstraint(
            "session_id", "position", name="uq_prism_onboarding_questions_session_position"
        ),
        sa.UniqueConstraint("session_id", "key", name="uq_prism_onboarding_questions_session_key"),
    )
    op.create_index(
        "ix_prism_onboarding_questions_session_id", "prism_onboarding_questions", ["session_id"]
    )
    op.create_table(
        "prism_onboarding_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "selected_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("custom_text", sa.Text()),
        sa.Column("skipped", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["prism_onboarding_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["prism_onboarding_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prism_onboarding_answers")),
        sa.UniqueConstraint("session_id", "question_id"),
    )
    op.create_index(
        "ix_prism_onboarding_answers_session_id", "prism_onboarding_answers", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_prism_onboarding_answers_session_id", table_name="prism_onboarding_answers")
    op.drop_table("prism_onboarding_answers")
    op.drop_index(
        "ix_prism_onboarding_questions_session_id", table_name="prism_onboarding_questions"
    )
    op.drop_table("prism_onboarding_questions")
    op.drop_table("prism_onboarding_sessions")
    onboarding_status.drop(op.get_bind(), checkfirst=True)
