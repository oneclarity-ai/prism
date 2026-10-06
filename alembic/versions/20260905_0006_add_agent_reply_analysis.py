"""add auditable agent reply analysis

Revision ID: 20260905_0006
Revises: 20260905_0005
Create Date: 2026-09-05 00:00:06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260905_0006"
down_revision: Union[str, Sequence[str], None] = "20260905_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    agent_run_status = postgresql.ENUM(
        "PENDING", "COMPLETED", "SKIPPED", "FAILED", name="agent_run_status", create_type=False
    )
    agent_analysis_type = postgresql.ENUM(
        "BLOCKER", "UPDATE", "UNCLEAR", name="agent_analysis_type", create_type=False
    )
    agent_run_status.create(op.get_bind(), checkfirst=True)
    agent_analysis_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", agent_run_status, nullable=False),
        sa.Column("analysis_type", agent_analysis_type, nullable=True),
        sa.Column("model_deployment", sa.String(length=255), nullable=True),
        sa.Column("completed_summary", sa.Text(), nullable=True),
        sa.Column("today_summary", sa.Text(), nullable=True),
        sa.Column("blocker_description", sa.Text(), nullable=True),
        sa.Column("dependency_owner_name", sa.String(length=255), nullable=True),
        sa.Column("dependency_owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_reply_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dependency_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("needs_yash_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["inbound_message_id"], ["messages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dependency_owner_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["blocker_id"], ["blockers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_reply_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dependency_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id"),
    )
    op.create_index(op.f("ix_agent_runs_source_employee_id"), "agent_runs", ["source_employee_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)
    op.create_index(op.f("ix_agent_runs_analysis_type"), "agent_runs", ["analysis_type"], unique=False)
    op.create_index(op.f("ix_agent_runs_dependency_owner_id"), "agent_runs", ["dependency_owner_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_blocker_id"), "agent_runs", ["blocker_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_processed_at"), "agent_runs", ["processed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_processed_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_blocker_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_dependency_owner_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_analysis_type"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_source_employee_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    sa.Enum(name="agent_analysis_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="agent_run_status").drop(op.get_bind(), checkfirst=True)
