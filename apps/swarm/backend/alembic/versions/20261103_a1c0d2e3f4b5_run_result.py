"""run result (structured results and files of a generic task)

Revision ID: a1c0d2e3f4b5
Revises: 08aad14daed8
Create Date: 2026-11-03 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1c0d2e3f4b5"
down_revision: Union[str, Sequence[str], None] = "08aad14daed8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "result")
