"""scope automation runs to explicit employees

Revision ID: 20260917_0014
Revises: 20260917_0013
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260917_0014"
down_revision = "20260917_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_runs",
        sa.Column(
            "target_employee_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE automation_runs AS run
        SET target_employee_ids = COALESCE((
            SELECT jsonb_agg(DISTINCT action.employee_id::text)
            FROM automation_actions AS action
            WHERE action.employee_id IS NOT NULL
              AND action.executed_at >= run.started_at
              AND (run.stopped_at IS NULL OR action.executed_at <= run.stopped_at)
        ), '[]'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_column("automation_runs", "target_employee_ids")
