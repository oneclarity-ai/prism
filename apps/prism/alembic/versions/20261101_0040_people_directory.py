"""People directory: org fields on employees, per-Prism people visibility.

Revision ID: 20261101_0040
Revises: 20261031_0039
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261101_0040"
down_revision = "20261031_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("department", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("responsibilities", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "employees",
        sa.Column(
            "field_overrides",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "employees",
        sa.Column("in_chats", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("employees", sa.Column("last_chat_at", sa.DateTime(timezone=True)))
    op.add_column("employees", sa.Column("directory_synced_at", sa.DateTime(timezone=True)))
    op.add_column(
        "prisms",
        sa.Column("people_scope", sa.String(length=20), nullable=False, server_default="all"),
    )
    op.create_table(
        "prism_people",
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prism_id", "employee_id"),
    )


def downgrade() -> None:
    op.drop_table("prism_people")
    op.drop_column("prisms", "people_scope")
    for column in (
        "directory_synced_at",
        "last_chat_at",
        "in_chats",
        "field_overrides",
        "notes",
        "responsibilities",
        "department",
    ):
        op.drop_column("employees", column)
