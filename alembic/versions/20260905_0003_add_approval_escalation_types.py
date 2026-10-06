"""add approval escalation types

Revision ID: 20260905_0003
Revises: 20260905_0002
Create Date: 2026-09-05 00:00:02

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260905_0003"
down_revision: Union[str, Sequence[str], None] = "20260905_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE escalation_type ADD VALUE IF NOT EXISTS 'ARCHITECTURE_CHANGE'")
    op.execute("ALTER TYPE escalation_type ADD VALUE IF NOT EXISTS 'PROJECT_DEADLINE_CHANGE'")
    op.execute("ALTER TYPE escalation_type ADD VALUE IF NOT EXISTS 'PRODUCTION_DEPLOYMENT'")
    op.execute("ALTER TYPE escalation_type ADD VALUE IF NOT EXISTS 'UNCERTAINTY'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed without rebuilding the type.
    pass
