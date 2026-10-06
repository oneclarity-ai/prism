"""Generalize manager-specific schema names from private pre-release builds.

Revision ID: 20261006_0017
Revises: 20260918_0016
Create Date: 2026-10-06
"""

import re

import sqlalchemy as sa

from alembic import op

revision = "20261006_0017"
down_revision = "20260918_0016"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _legacy_column(table_name: str, prefix: str, suffix: str, current: str) -> str | None:
    matches = sorted(
        column
        for column in _columns(table_name)
        if column != current and column.startswith(prefix) and column.endswith(suffix)
    )
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous legacy columns on {table_name}: {matches}")
    return matches[0] if matches else None


def _drop_single_column_indexes(table_name: str, column_name: str) -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    for index in indexes:
        if index.get("column_names") == [column_name] and index.get("name"):
            op.drop_index(str(index["name"]), table_name=table_name)


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
    legacy_approval = _legacy_column(
        "escalations", "requires_", "_approval", "requires_manager_approval"
    )
    if legacy_approval:
        _drop_single_column_indexes("escalations", legacy_approval)
        op.alter_column(
            "escalations",
            legacy_approval,
            new_column_name="requires_manager_approval",
        )
        op.create_index(
            "ix_escalations_requires_manager_approval",
            "escalations",
            ["requires_manager_approval"],
        )

    legacy_review = _legacy_column("agent_runs", "needs_", "_review", "needs_manager_review")
    if legacy_review:
        op.alter_column(
            "agent_runs",
            legacy_review,
            new_column_name="needs_manager_review",
        )

    sender_labels = _enum_labels("sender_type")
    legacy_labels = sender_labels - {"EMPLOYEE", "AGENT", "MANAGER", "SYSTEM"}
    if "MANAGER" not in sender_labels and len(legacy_labels) == 1:
        legacy_label = legacy_labels.pop()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", legacy_label):
            raise RuntimeError("Unsafe legacy sender_type label")
        op.execute("ALTER TYPE sender_type RENAME VALUE '{}' TO 'MANAGER'".format(legacy_label))
    elif legacy_labels:
        raise RuntimeError(f"Ambiguous legacy sender_type labels: {sorted(legacy_labels)}")


def downgrade() -> None:
    escalation_columns = _columns("escalations")
    if "requires_manager_approval" in escalation_columns:
        op.drop_index("ix_escalations_requires_manager_approval", table_name="escalations")
        op.alter_column(
            "escalations",
            "requires_manager_approval",
            new_column_name="requires_operator_approval",
        )
        op.create_index(
            "ix_escalations_requires_operator_approval",
            "escalations",
            ["requires_operator_approval"],
        )

    agent_run_columns = _columns("agent_runs")
    if "needs_manager_review" in agent_run_columns:
        op.alter_column(
            "agent_runs",
            "needs_manager_review",
            new_column_name="needs_operator_review",
        )

    sender_labels = _enum_labels("sender_type")
    if "MANAGER" in sender_labels and "OPERATOR" not in sender_labels:
        op.execute("ALTER TYPE sender_type RENAME VALUE 'MANAGER' TO 'OPERATOR'")
