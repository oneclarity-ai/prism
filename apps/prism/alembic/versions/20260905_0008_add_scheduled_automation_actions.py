"""add idempotent scheduled automation actions

Revision ID: 20260905_0008
Revises: 20260905_0007
Create Date: 2026-09-05 00:00:08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260905_0008"
down_revision: Union[str, Sequence[str], None] = "20260905_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    action_type = postgresql.ENUM(
        "DAILY_CHECKIN", "NO_RESPONSE_FOLLOWUP", "MISSED_COMMITMENT_FOLLOWUP",
        "DAILY_DIGEST", "ESCALATION_NOTIFICATION", name="automation_action_type", create_type=False,
    )
    action_status = postgresql.ENUM(
        "DELIVERED", "SKIPPED", "FAILED", name="automation_action_status", create_type=False,
    )
    action_type.create(op.get_bind(), checkfirst=True)
    action_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "automation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", action_type, nullable=False),
        sa.Column("status", action_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("escalation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["commitment_id"], ["commitments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["blocker_id"], ["blockers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["escalation_id"], ["escalations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in ("action_type", "status", "employee_id", "commitment_id", "blocker_id", "escalation_id", "executed_at"):
        op.create_index(op.f("ix_automation_actions_" + column), "automation_actions", [column], unique=False)


def downgrade() -> None:
    for column in ("executed_at", "escalation_id", "blocker_id", "commitment_id", "employee_id", "status", "action_type"):
        op.drop_index(op.f("ix_automation_actions_" + column), table_name="automation_actions")
    op.drop_table("automation_actions")
    sa.Enum(name="automation_action_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="automation_action_type").drop(op.get_bind(), checkfirst=True)
