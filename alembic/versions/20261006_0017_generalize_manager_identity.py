"""generalize manager-specific schema names

Revision ID: 20261006_0017
Revises: 20260918_0016
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0017"
down_revision = "20260918_0016"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _enum_labels(type_name: str) -> set[str]:
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
            WHERE pg_type.typname = :type_name
            """
        ),
        {"type_name": type_name},
    )
    return {str(row[0]) for row in rows}


def upgrade() -> None:
    escalation_columns = _columns("escalations")
    if "requires_yash_approval" in escalation_columns:
        op.drop_index("ix_escalations_requires_yash_approval", table_name="escalations")
        op.alter_column(
            "escalations",
            "requires_yash_approval",
            new_column_name="requires_manager_approval",
        )
        op.create_index(
            "ix_escalations_requires_manager_approval",
            "escalations",
            ["requires_manager_approval"],
        )

    agent_run_columns = _columns("agent_runs")
    if "needs_yash_review" in agent_run_columns:
        op.alter_column(
            "agent_runs",
            "needs_yash_review",
            new_column_name="needs_manager_review",
        )

    sender_labels = _enum_labels("sender_type")
    if "YASH" in sender_labels and "MANAGER" not in sender_labels:
        op.execute("ALTER TYPE sender_type RENAME VALUE 'YASH' TO 'MANAGER'")


def downgrade() -> None:
    escalation_columns = _columns("escalations")
    if "requires_manager_approval" in escalation_columns:
        op.drop_index("ix_escalations_requires_manager_approval", table_name="escalations")
        op.alter_column(
            "escalations",
            "requires_manager_approval",
            new_column_name="requires_yash_approval",
        )
        op.create_index(
            "ix_escalations_requires_yash_approval",
            "escalations",
            ["requires_yash_approval"],
        )

    agent_run_columns = _columns("agent_runs")
    if "needs_manager_review" in agent_run_columns:
        op.alter_column(
            "agent_runs",
            "needs_manager_review",
            new_column_name="needs_yash_review",
        )

    sender_labels = _enum_labels("sender_type")
    if "MANAGER" in sender_labels and "YASH" not in sender_labels:
        op.execute("ALTER TYPE sender_type RENAME VALUE 'MANAGER' TO 'YASH'")
