"""Add a chosen colour to each Prism.

Revision ID: 20261031_0039
Revises: 20261030_0038
Create Date: 2026-10-31
"""

import sqlalchemy as sa

from alembic import op

revision = "20261031_0039"
down_revision = "20261030_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means "not chosen yet"; the UI derives a stable colour from the name until one is picked.
    op.add_column("prisms", sa.Column("color", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("prisms", "color")
