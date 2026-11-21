"""durable run leases and checkpoints

Revision ID: d4f6a8b0c2e4
Revises: c3e2f5a7b8d9
Create Date: 2026-11-03 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4f6a8b0c2e4"
down_revision: str | Sequence[str] | None = "c3e2f5a7b8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("operation_key", sa.String(200)))
    op.create_unique_constraint("uq_tasks_org_operation_key", "tasks", ["org_id", "operation_key"])
    op.add_column("runs", sa.Column("operation_key", sa.String(200)))
    op.create_unique_constraint("uq_runs_org_operation_key", "runs", ["org_id", "operation_key"])
    op.add_column("approvals", sa.Column("decision_key", sa.String(200)))
    op.create_unique_constraint("uq_approvals_org_decision_key", "approvals", ["org_id", "decision_key"])
    op.add_column("runs", sa.Column("lease_owner", sa.String(200)))
    op.add_column("runs", sa.Column("lease_token", postgresql.UUID(as_uuid=True)))
    op.add_column("runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("runs", sa.Column("attempt", sa.Integer(), server_default="0", nullable=False))
    op.add_column("runs", sa.Column("checkpoint_at", sa.DateTime(timezone=True)))
    op.add_column("runs", sa.Column("active_tool", sa.String(120)))
    op.add_column("runs", sa.Column("active_tool_risky", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index("ix_runs_lease_owner", "runs", ["lease_owner"])
    op.create_index("ix_runs_lease_token", "runs", ["lease_token"])
    op.create_index("ix_runs_lease_expires_at", "runs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_lease_expires_at", table_name="runs")
    op.drop_index("ix_runs_lease_token", table_name="runs")
    op.drop_index("ix_runs_lease_owner", table_name="runs")
    for name in (
        "active_tool_risky",
        "active_tool",
        "checkpoint_at",
        "attempt",
        "lease_expires_at",
        "lease_token",
        "lease_owner",
    ):
        op.drop_column("runs", name)
    op.drop_constraint("uq_approvals_org_decision_key", "approvals", type_="unique")
    op.drop_column("approvals", "decision_key")
    op.drop_constraint("uq_runs_org_operation_key", "runs", type_="unique")
    op.drop_column("runs", "operation_key")
    op.drop_constraint("uq_tasks_org_operation_key", "tasks", type_="unique")
    op.drop_column("tasks", "operation_key")
