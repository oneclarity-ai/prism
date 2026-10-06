"""add commitment missed reason

Revision ID: 20260905_0002
Revises: 20260905_0001
Create Date: 2026-09-05 00:00:01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260905_0002"
down_revision: Union[str, Sequence[str], None] = "20260905_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commitments", sa.Column("missed_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("commitments", "missed_reason")
