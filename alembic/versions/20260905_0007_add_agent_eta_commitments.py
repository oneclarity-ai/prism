"""add agent ETA commitment audit fields

Revision ID: 20260905_0007
Revises: 20260905_0006
Create Date: 2026-09-05 00:00:07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260905_0007"
down_revision: Union[str, Sequence[str], None] = "20260905_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("eta_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_agent_runs_commitment_id_commitments"),
        "agent_runs",
        "commitments",
        ["commitment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_agent_runs_commitment_id"), "agent_runs", ["commitment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_commitment_id"), table_name="agent_runs")
    op.drop_constraint(op.f("fk_agent_runs_commitment_id_commitments"), "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "commitment_id")
    op.drop_column("agent_runs", "eta_deadline")
