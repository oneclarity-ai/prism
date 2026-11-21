"""add reopened dependency history

Revision ID: 20260917_0013
Revises: 20260917_0012
Create Date: 2026-09-17 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_0013"
down_revision: Union[str, Sequence[str], None] = "20260917_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("dependency_edges")}
    if "reopened_from_id" not in columns:
        op.add_column("dependency_edges", sa.Column("reopened_from_id", sa.UUID(), nullable=True))
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("dependency_edges")}
    fk_name = op.f("fk_dependency_edges_reopened_from_id_dependency_edges")
    if fk_name not in foreign_keys:
        op.create_foreign_key(
            fk_name, "dependency_edges", "dependency_edges",
            ["reopened_from_id"], ["id"], ondelete="SET NULL",
        )
    indexes = {item["name"] for item in inspector.get_indexes("dependency_edges")}
    index_name = op.f("ix_dependency_edges_reopened_from_id")
    if index_name not in indexes:
        op.create_index(index_name, "dependency_edges", ["reopened_from_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_dependency_edges_reopened_from_id"), table_name="dependency_edges")
    op.drop_constraint(op.f("fk_dependency_edges_reopened_from_id_dependency_edges"), "dependency_edges", type_="foreignkey")
    op.drop_column("dependency_edges", "reopened_from_id")
