"""QA tester Prism: website test runs and relayed bug-filing approvals.

Revision ID: 20261102_0042
Revises: 20261101_0041
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261102_0042"
down_revision = "20261101_0041"
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
    op.create_table(
        "qa_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prism_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prisms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("swarm_target_id", sa.String(64)),
        sa.Column("swarm_task_id", sa.String(64)),
        sa.Column("swarm_run_id", sa.String(64)),
        sa.Column("swarm_run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_url", sa.String(2048)),
        sa.Column("current_activity", sa.String(300)),
        sa.Column("activity_log", postgresql.JSONB(), nullable=False),
        sa.Column("latest_screenshot_id", sa.String(64)),
        sa.Column("screenshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("cases", postgresql.JSONB(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("report", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        *_ts(),
    )
    op.create_index("ix_qa_runs_prism_id", "qa_runs", ["prism_id"])
    op.create_index("ix_qa_runs_thread_id", "qa_runs", ["thread_id"])
    op.create_index("ix_qa_runs_state", "qa_runs", ["state"])
    op.create_table(
        "qa_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "qa_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("qa_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("swarm_approval_id", sa.String(64), nullable=False, unique=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *_ts(),
    )
    op.create_index("ix_qa_approvals_qa_run_id", "qa_approvals", ["qa_run_id"])


def downgrade() -> None:
    op.drop_table("qa_approvals")
    op.drop_table("qa_runs")
