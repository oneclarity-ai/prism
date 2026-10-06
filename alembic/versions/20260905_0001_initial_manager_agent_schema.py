"""initial manager agent schema

Revision ID: 20260905_0001
Revises:
Create Date: 2026-09-05 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260905_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("teams_user_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["manager_id"], ["employees.id"], name=op.f("fk_employees_manager_id_employees"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("email", name=op.f("uq_employees_email")),
        sa.UniqueConstraint("teams_user_id", name=op.f("uq_employees_teams_user_id")),
    )
    op.create_index(op.f("ix_employees_manager_id"), "employees", ["manager_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("PLANNING", "ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED", name="project_status"), nullable=False),
        sa.Column("priority", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="priority"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["employees.id"], name=op.f("fk_projects_owner_id_employees"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=False)
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_index(op.f("ix_projects_priority"), "projects", ["priority"], unique=False)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)
    op.create_index(op.f("ix_projects_target_date"), "projects", ["target_date"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED", name="task_status"), nullable=False),
        sa.Column("priority", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="priority"), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["employees.id"], name=op.f("fk_tasks_owner_id_employees"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_tasks_project_id_projects"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_deadline"), "tasks", ["deadline"], unique=False)
    op.create_index(op.f("ix_tasks_owner_id"), "tasks", ["owner_id"], unique=False)
    op.create_index(op.f("ix_tasks_priority"), "tasks", ["priority"], unique=False)
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)

    op.create_table(
        "blockers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocked_employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "RESOLVED", name="blocker_status"), nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="blocker_severity"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blocked_employee_id"], ["employees.id"], name=op.f("fk_blockers_blocked_employee_id_employees"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dependency_owner_id"], ["employees.id"], name=op.f("fk_blockers_dependency_owner_id_employees"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_blockers_task_id_tasks"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blockers")),
    )
    op.create_index(op.f("ix_blockers_blocked_employee_id"), "blockers", ["blocked_employee_id"], unique=False)
    op.create_index(op.f("ix_blockers_dependency_owner_id"), "blockers", ["dependency_owner_id"], unique=False)
    op.create_index(op.f("ix_blockers_severity"), "blockers", ["severity"], unique=False)
    op.create_index(op.f("ix_blockers_status"), "blockers", ["status"], unique=False)
    op.create_index(op.f("ix_blockers_task_id"), "blockers", ["task_id"], unique=False)

    op.create_table(
        "daily_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("update_date", sa.Date(), nullable=False),
        sa.Column("completed_summary", sa.Text(), nullable=True),
        sa.Column("today_summary", sa.Text(), nullable=True),
        sa.Column("blocker_summary", sa.Text(), nullable=True),
        sa.Column("raw_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_daily_updates_employee_id_employees"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_updates")),
        sa.UniqueConstraint("employee_id", "update_date", name=op.f("uq_daily_updates_employee_daily_update")),
    )
    op.create_index(op.f("ix_daily_updates_employee_id"), "daily_updates", ["employee_id"], unique=False)
    op.create_index(op.f("ix_daily_updates_update_date"), "daily_updates", ["update_date"], unique=False)

    op.create_table(
        "commitments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "COMPLETED", "MISSED", "CANCELLED", "SUPERSEDED", name="commitment_status"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("missed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revised_from_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["blockers.id"], name=op.f("fk_commitments_blocker_id_blockers"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_commitments_employee_id_employees"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revised_from_id"], ["commitments.id"], name=op.f("fk_commitments_revised_from_id_commitments"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_commitments_task_id_tasks"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commitments")),
    )
    op.create_index(op.f("ix_commitments_blocker_id"), "commitments", ["blocker_id"], unique=False)
    op.create_index(op.f("ix_commitments_deadline"), "commitments", ["deadline"], unique=False)
    op.create_index(op.f("ix_commitments_employee_id"), "commitments", ["employee_id"], unique=False)
    op.create_index(op.f("ix_commitments_missed_at"), "commitments", ["missed_at"], unique=False)
    op.create_index(op.f("ix_commitments_revised_from_id"), "commitments", ["revised_from_id"], unique=False)
    op.create_index(op.f("ix_commitments_status"), "commitments", ["status"], unique=False)
    op.create_index(op.f("ix_commitments_task_id"), "commitments", ["task_id"], unique=False)

    op.create_table(
        "escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("escalation_type", sa.Enum("BLOCKER", "MISSED_COMMITMENT", "PROJECT_RISK", "APPROVAL_REQUIRED", "OTHER", name="escalation_type"), nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="blocker_severity"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("OPEN", "ACKNOWLEDGED", "RESOLVED", name="escalation_status"), nullable=False),
        sa.Column("requires_yash_approval", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_escalations_employee_id_employees"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_escalations_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_escalations_task_id_tasks"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalations")),
    )
    op.create_index(op.f("ix_escalations_employee_id"), "escalations", ["employee_id"], unique=False)
    op.create_index(op.f("ix_escalations_escalation_type"), "escalations", ["escalation_type"], unique=False)
    op.create_index(op.f("ix_escalations_project_id"), "escalations", ["project_id"], unique=False)
    op.create_index(op.f("ix_escalations_requires_yash_approval"), "escalations", ["requires_yash_approval"], unique=False)
    op.create_index(op.f("ix_escalations_severity"), "escalations", ["severity"], unique=False)
    op.create_index(op.f("ix_escalations_status"), "escalations", ["status"], unique=False)
    op.create_index(op.f("ix_escalations_task_id"), "escalations", ["task_id"], unique=False)

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.Enum("TEAMS", "OUTLOOK", "GMAIL", "INTERNAL", name="conversation_channel"), nullable=False),
        sa.Column("external_conversation_id", sa.String(length=255), nullable=True),
        sa.Column("conversation_type", sa.Enum("DIRECT", "GROUP", "MEETING", name="conversation_type"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_conversations_employee_id_employees"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("external_conversation_id", name=op.f("uq_conversations_external_conversation_id")),
    )
    op.create_index(op.f("ix_conversations_channel"), "conversations", ["channel"], unique=False)
    op.create_index(op.f("ix_conversations_employee_id"), "conversations", ["employee_id"], unique=False)
    op.create_index(op.f("ix_conversations_last_message_at"), "conversations", ["last_message_at"], unique=False)
    op.create_index(op.f("ix_conversations_conversation_type"), "conversations", ["conversation_type"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("direction", sa.Enum("INBOUND", "OUTBOUND", name="message_direction"), nullable=False),
        sa.Column("sender_type", sa.Enum("EMPLOYEE", "AGENT", "YASH", "SYSTEM", name="sender_type"), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], name=op.f("fk_messages_conversation_id_conversations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name=op.f("fk_messages_employee_id_employees"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("external_message_id", name=op.f("uq_messages_external_message_id")),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_messages_direction"), "messages", ["direction"], unique=False)
    op.create_index(op.f("ix_messages_employee_id"), "messages", ["employee_id"], unique=False)
    op.create_index(op.f("ix_messages_sender_type"), "messages", ["sender_type"], unique=False)


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("escalations")
    op.drop_table("commitments")
    op.drop_table("daily_updates")
    op.drop_table("blockers")
    op.drop_table("tasks")
    op.drop_table("projects")
    op.drop_table("employees")
