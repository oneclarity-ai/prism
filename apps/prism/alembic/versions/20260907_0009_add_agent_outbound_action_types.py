"""add idempotent management-agent outbound action types

Revision ID: 20260907_0009
Revises: 4a7274691244
Create Date: 2026-09-07 17:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260907_0009"
down_revision: Union[str, Sequence[str], None] = "4a7274691244"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL enum values are append-only.  IF NOT EXISTS makes this safe for
    # development databases where a partial manual attempt may have occurred.
    op.execute("ALTER TYPE automation_action_type ADD VALUE IF NOT EXISTS 'BLOCKER_SOURCE_ACKNOWLEDGEMENT'")
    op.execute("ALTER TYPE automation_action_type ADD VALUE IF NOT EXISTS 'BLOCKER_OWNER_REQUEST'")
    op.execute("ALTER TYPE automation_action_type ADD VALUE IF NOT EXISTS 'BLOCKER_OWNER_CLARIFICATION'")
    op.execute("ALTER TYPE automation_action_status ADD VALUE IF NOT EXISTS 'PENDING'")


def downgrade() -> None:
    # PostgreSQL does not safely remove enum values.  Keeping them is harmless
    # and avoids a destructive enum recreation on a live management database.
    pass
