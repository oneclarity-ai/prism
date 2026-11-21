"""precise run cost (cached tokens, wider cost columns)

Revision ID: b2d1e4f6a7c8
Revises: a1c0d2e3f4b5
Create Date: 2026-11-04 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2d1e4f6a7c8"
down_revision: Union[str, Sequence[str], None] = "a1c0d2e3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("cached_input_tokens", sa.Integer(), server_default="0", nullable=False))
    for table in ("runs", "budget_ledger"):
        op.alter_column(table, "cost_usd", type_=sa.Numeric(18, 10), existing_nullable=False)


def downgrade() -> None:
    for table in ("runs", "budget_ledger"):
        op.alter_column(table, "cost_usd", type_=sa.Numeric(10, 4), existing_nullable=False)
    op.drop_column("runs", "cached_input_tokens")
