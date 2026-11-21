"""backfill cached input tokens from each run's last usage event

Revision ID: c3e2f5a7b8d9
Revises: b2d1e4f6a7c8
Create Date: 2026-11-04 09:30:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3e2f5a7b8d9"
down_revision: Union[str, Sequence[str], None] = "b2d1e4f6a7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE runs r SET cached_input_tokens = LEAST(r.input_tokens, COALESCE((
            SELECT (e.payload->>'cached_tokens')::int FROM run_events e
            WHERE e.run_id = r.id AND e.type = 'usage' AND e.payload ? 'cached_tokens'
            ORDER BY e.seq DESC LIMIT 1), 0))
        WHERE r.cached_input_tokens = 0
        """
    )


def downgrade() -> None:
    pass
