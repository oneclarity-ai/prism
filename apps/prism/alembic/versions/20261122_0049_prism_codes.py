"""Stable, automatically assigned public Prism codes; existing UUIDs remain unchanged.

Revision ID: 20261122_0049
Revises: 20261122_0048
"""

import sqlalchemy as sa

from alembic import op

revision = "20261122_0049"
down_revision = "20261122_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE prism_code_seq")
    op.add_column("prisms", sa.Column("code", sa.String(24), nullable=True))
    op.execute("""
        WITH ordered AS MATERIALIZED (SELECT id FROM prisms ORDER BY created_at, id),
        numbered AS MATERIALIZED (SELECT id, nextval('prism_code_seq') AS number FROM ordered)
        UPDATE prisms SET code = 'PR-' || numbered.number::text FROM numbered
        WHERE prisms.id = numbered.id
    """)
    op.alter_column(
        "prisms",
        "code",
        nullable=False,
        server_default=sa.text("'PR-' || nextval('prism_code_seq')::text"),
    )
    op.create_unique_constraint("uq_prisms_code", "prisms", ["code"])
    op.execute("ALTER SEQUENCE prism_code_seq OWNED BY prisms.code")


def downgrade() -> None:
    op.drop_constraint("uq_prisms_code", "prisms", type_="unique")
    op.drop_column("prisms", "code")
    op.execute("DROP SEQUENCE IF EXISTS prism_code_seq")
