"""Keep automatically created onboarding skills private to their Prism.

Revision ID: 20261122_0048
Revises: 20261121_0047
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261122_0048"
down_revision = "20261121_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prism_skills", sa.Column("owner_prism_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_prism_skills_owner_prism_id_prisms",
        "prism_skills",
        "prisms",
        ["owner_prism_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_prism_skills_owner_prism_id", "prism_skills", ["owner_prism_id"])
    op.alter_column(
        "prism_skills", "normalized_name", existing_type=sa.String(360), type_=sa.String(400)
    )


def downgrade() -> None:
    # Never publish private instructions by dropping their ownership marker.
    op.execute("DELETE FROM prism_skills WHERE owner_prism_id IS NOT NULL")
    op.alter_column(
        "prism_skills", "normalized_name", existing_type=sa.String(400), type_=sa.String(360)
    )
    op.drop_index("ix_prism_skills_owner_prism_id", table_name="prism_skills")
    op.drop_constraint("fk_prism_skills_owner_prism_id_prisms", "prism_skills", type_="foreignkey")
    op.drop_column("prism_skills", "owner_prism_id")
