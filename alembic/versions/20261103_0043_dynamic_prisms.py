"""Dynamic Prisms: capabilities, logins policy, computers, saved logins, generic runs.

Revision ID: 20261103_0043
Revises: 20261102_0042
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261103_0043"
down_revision = "20261102_0042"
branch_labels = None
depends_on = None

_ts = lambda: [  # noqa: E731
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
]


def upgrade() -> None:
    op.add_column(
        "prisms",
        sa.Column(
            "capabilities",
            postgresql.JSONB(),
            server_default='["browser"]',
            nullable=False,
        ),
    )
    op.add_column(
        "prisms",
        sa.Column("logins_policy", sa.String(10), server_default="never", nullable=False),
    )
    op.add_column("prisms", sa.Column("role_instructions", sa.Text()))
    # Executive assistants already read Teams: keep that capability for them.
    op.execute(
        "UPDATE prisms SET capabilities = '[\"browser\", \"teams\"]'::jsonb "
        "WHERE template_key = 'executive_assistant'"
    )
    op.add_column("qa_runs", sa.Column("kind", sa.String(12), server_default="qa", nullable=False))
    op.add_column(
        "qa_runs",
        sa.Column("checklist", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column("qa_runs", sa.Column("latest_frame_id", sa.String(64)))
    op.add_column(
        "qa_runs", sa.Column("frame_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "qa_runs",
        sa.Column("file_ids", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "qa_approvals",
        sa.Column("kind", sa.String(20), server_default="bug_filing", nullable=False),
    )
    op.create_table(
        "prism_computers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("computer_key", sa.String(64), nullable=False, unique=True),
        sa.Column("swarm_agent_id", sa.String(64)),
        sa.Column("agent_hash", sa.String(64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        *_ts(),
    )
    op.create_table(
        "prism_logins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(300), nullable=False),
        sa.Column("username_masked", sa.String(120), nullable=False),
        sa.Column("swarm_secret_id", sa.String(64)),
        sa.Column("remember", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("prism_id", "origin"),
        *_ts(),
    )
    op.create_index("ix_prism_logins_prism", "prism_logins", ["prism_id"])


def downgrade() -> None:
    op.drop_index("ix_prism_logins_prism", table_name="prism_logins")
    op.drop_table("prism_logins")
    op.drop_table("prism_computers")
    op.drop_column("qa_approvals", "kind")
    for column in ("file_ids", "frame_count", "latest_frame_id", "checklist", "kind"):
        op.drop_column("qa_runs", column)
    for column in ("role_instructions", "logins_policy", "capabilities"):
        op.drop_column("prisms", column)
