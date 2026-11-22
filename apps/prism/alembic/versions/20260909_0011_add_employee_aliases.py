"""add explicit employee aliases

Revision ID: 20260909_0011
Revises: 524786cdfa8a
Create Date: 2026-09-09 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260909_0011"
down_revision: Union[str, Sequence[str], None] = "524786cdfa8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"],
            name=op.f("fk_employee_aliases_employee_id_employees"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_aliases")),
        sa.UniqueConstraint("normalized_alias", name=op.f("uq_employee_aliases_normalized_alias")),
    )
    op.create_index(
        op.f("ix_employee_aliases_employee_id"), "employee_aliases", ["employee_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_employee_aliases_employee_id"), table_name="employee_aliases")
    op.drop_table("employee_aliases")
