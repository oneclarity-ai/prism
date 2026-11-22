"""Mark the user's reporting team on employees.

Revision ID: 20261101_0041
Revises: 20261101_0040
Create Date: 2026-11-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261101_0041"
down_revision = "20261101_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees", sa.Column("in_team", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("employees", "in_team")
