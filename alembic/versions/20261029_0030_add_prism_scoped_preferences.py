"""Scope v2.2 remembered preferences to a private Prism.

Revision ID: 20261029_0030
Revises: 20261029_0029
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0030"
down_revision = "20261029_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL is intentional: it preserves existing v2.1 preferences as legacy
    # data rather than assigning private context to an arbitrary new Prism.
    op.add_column(
        "agent_preferences", sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_agent_preferences_prism_id_prisms",
        "agent_preferences",
        "prisms",
        ["prism_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_agent_preferences_prism_id", "agent_preferences", ["prism_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_preferences_prism_id", table_name="agent_preferences")
    op.drop_constraint("fk_agent_preferences_prism_id_prisms", "agent_preferences", type_="foreignkey")
    op.drop_column("agent_preferences", "prism_id")
