"""Add base_url and api_version to provider_credentials for multi-provider BYOK.

Revision ID: 20261122_0051
Revises: 20261122_0050
Create Date: 2026-11-22
"""

import sqlalchemy as sa

from alembic import op

revision = "20261122_0051"
down_revision = "20261122_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_credentials", sa.Column("base_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "provider_credentials", sa.Column("api_version", sa.String(length=40), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("provider_credentials", "api_version")
    op.drop_column("provider_credentials", "base_url")
