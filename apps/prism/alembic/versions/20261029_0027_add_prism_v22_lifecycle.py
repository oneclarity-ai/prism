"""Add Prism v2.2 identity, lifecycle events, and per-Prism conversation ownership.

Revision ID: 20261029_0027
Revises: 20261029_0026
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0027"
down_revision = "20261029_0026"
branch_labels = None
depends_on = None

prism_state = postgresql.ENUM(
    "DRAFT",
    "ONBOARDING",
    "AWAITING_CONFIRMATION",
    "ACTIVE",
    "PAUSED",
    "ARCHIVED",
    name="prism_lifecycle_state",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    prism_state.create(bind, checkfirst=True)

    op.create_table(
        "prisms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("template_key", sa.String(length=80), server_default="blank", nullable=False),
        sa.Column("template_version", sa.String(length=80)),
        sa.Column(
            "state", prism_state, server_default="DRAFT", nullable=False
        ),
        sa.Column("lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prisms")),
    )
    op.create_index("ix_prisms_state", "prisms", ["state"])
    op.create_index(
        "uq_prisms_active_normalized_name",
        "prisms",
        ["normalized_name"],
        unique=True,
        postgresql_where=sa.text("state != 'ARCHIVED'"),
    )

    op.create_table(
        "prism_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("previous_state", prism_state),
        sa.Column("target_state", prism_state, nullable=False),
        sa.Column("actor", sa.String(length=80), server_default="local_manager", nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prism_lifecycle_events")),
        sa.UniqueConstraint("prism_id", "sequence"),
    )
    op.create_index(
        "ix_prism_lifecycle_events_prism_id", "prism_lifecycle_events", ["prism_id"]
    )

    op.add_column(
        "agent_threads", sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_agent_threads_prism_id_prisms",
        "agent_threads",
        "prisms",
        ["prism_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_agent_threads_prism_id", "agent_threads", ["prism_id"])

    # v2.1 has one global canonical conversation. Phase 5 migrates it into an
    # Executive Assistant Prism. These two partial indexes preserve that legacy
    # invariant now and permit one canonical conversation for every future Prism.
    op.drop_index("uq_agent_threads_one_canonical", table_name="agent_threads")
    op.create_index(
        "uq_agent_threads_one_legacy_canonical",
        "agent_threads",
        ["is_canonical"],
        unique=True,
        postgresql_where=sa.text("is_canonical AND prism_id IS NULL"),
    )
    op.create_index(
        "uq_agent_threads_one_prism_canonical",
        "agent_threads",
        ["prism_id"],
        unique=True,
        postgresql_where=sa.text("is_canonical AND prism_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_threads_one_prism_canonical", table_name="agent_threads")
    op.drop_index("uq_agent_threads_one_legacy_canonical", table_name="agent_threads")
    op.create_index(
        "uq_agent_threads_one_canonical",
        "agent_threads",
        ["is_canonical"],
        unique=True,
        postgresql_where=sa.text("is_canonical"),
    )
    op.drop_index("ix_agent_threads_prism_id", table_name="agent_threads")
    op.drop_constraint("fk_agent_threads_prism_id_prisms", "agent_threads", type_="foreignkey")
    op.drop_column("agent_threads", "prism_id")
    op.drop_index("ix_prism_lifecycle_events_prism_id", table_name="prism_lifecycle_events")
    op.drop_table("prism_lifecycle_events")
    op.drop_index("uq_prisms_active_normalized_name", table_name="prisms")
    op.drop_index("ix_prisms_state", table_name="prisms")
    op.drop_table("prisms")
    prism_state.drop(op.get_bind(), checkfirst=True)
