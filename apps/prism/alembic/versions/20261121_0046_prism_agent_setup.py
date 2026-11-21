"""Prism owns its agent setup: tool grants and limits.

Revision ID: 20261121_0046
Revises: 20261120_0045
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261121_0046"
down_revision = "20261120_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prisms", sa.Column("tool_grants", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("prisms", sa.Column("max_turns", sa.Integer()))
    op.add_column("prisms", sa.Column("run_budget_usd", sa.Numeric(10, 2)))
    op.add_column("prisms", sa.Column("monthly_budget_usd", sa.Numeric(10, 2)))


def downgrade() -> None:
    op.drop_column("prisms", "monthly_budget_usd")
    op.drop_column("prisms", "run_budget_usd")
    op.drop_column("prisms", "max_turns")
    op.drop_column("prisms", "tool_grants")
