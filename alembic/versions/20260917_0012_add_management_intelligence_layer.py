"""add management intelligence layer

Revision ID: 20260917_0012
Revises: 20260909_0011
Create Date: 2026-09-17 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260917_0012"
down_revision: Union[str, Sequence[str], None] = "20260909_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commitments", sa.Column("source_message_id", sa.UUID(), nullable=True))
    op.add_column("commitments", sa.Column("confidence", sa.Float(), nullable=True))
    op.create_foreign_key(
        op.f("fk_commitments_source_message_id_messages"), "commitments", "messages",
        ["source_message_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_commitments_source_message_id"), "commitments", ["source_message_id"])

    op.add_column("conversation_questions", sa.Column("expected_answer_type", sa.String(40), nullable=True))
    op.add_column("conversation_questions", sa.Column("asked_to_employee_id", sa.UUID(), nullable=True))
    op.add_column("conversation_questions", sa.Column("related_commitment_id", sa.UUID(), nullable=True))
    op.add_column(
        "conversation_questions",
        sa.Column("status", sa.String(24), server_default="awaiting_response", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_conversation_questions_asked_to_employee_id_employees"),
        "conversation_questions", "employees", ["asked_to_employee_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_conversation_questions_related_commitment_id_commitments"),
        "conversation_questions", "commitments", ["related_commitment_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_conversation_questions_asked_to_employee_id"), "conversation_questions", ["asked_to_employee_id"])
    op.create_index(op.f("ix_conversation_questions_related_commitment_id"), "conversation_questions", ["related_commitment_id"])
    op.create_index(op.f("ix_conversation_questions_status"), "conversation_questions", ["status"])
    op.execute("UPDATE conversation_questions SET expected_answer_type = awaiting_field WHERE expected_answer_type IS NULL")
    op.execute("""
        UPDATE conversation_questions AS q
        SET asked_to_employee_id = c.employee_id
        FROM conversations AS c
        WHERE c.id = q.conversation_id AND q.asked_to_employee_id IS NULL
    """)

    op.create_table(
        "dependency_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_entity_type", sa.String(32), nullable=False),
        sa.Column("source_entity_id", sa.UUID(), nullable=False),
        sa.Column("target_entity_type", sa.String(32), nullable=False),
        sa.Column("target_entity_id", sa.UUID(), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("blocker_id", sa.UUID(), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("source_message_id", sa.UUID(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["blockers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["relation_type", "status", "blocker_id", "task_id", "project_id", "source_message_id", "valid_from", "valid_until"]:
        op.create_index(op.f("ix_dependency_edges_" + column), "dependency_edges", [column])
    op.create_index("ix_dependency_edges_source", "dependency_edges", ["source_entity_type", "source_entity_id", "status"])
    op.create_index("ix_dependency_edges_target", "dependency_edges", ["target_entity_type", "target_entity_id", "status"])

    op.create_table(
        "management_risks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column("risk_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_entity_type", sa.String(32), nullable=False),
        sa.Column("source_entity_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(64), nullable=False),
        sa.Column("affected_entities", postgresql.JSONB(), nullable=False),
        sa.Column("signals", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("deadline_at_risk", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_management_risks_fingerprint"),
    )
    for column in ["risk_type", "severity", "status", "source_entity_type", "source_entity_id", "deadline_at_risk", "last_evaluated_at", "resolved_at"]:
        op.create_index(op.f("ix_management_risks_" + column), "management_risks", [column])

    op.create_table(
        "management_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("trigger_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("target_employee_ids", postgresql.JSONB(), nullable=False),
        sa.Column("related_issue_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_management_decisions_idempotency_key"),
    )
    for column in ["trigger_type", "trigger_id", "action", "status", "related_issue_id"]:
        op.create_index(op.f("ix_management_decisions_" + column), "management_decisions", [column])

    op.create_table(
        "manager_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instruction_type", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("source_message_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["instruction_type", "scope", "employee_id", "project_id", "source_message_id", "is_active", "expires_at"]:
        op.create_index(op.f("ix_manager_feedback_" + column), "manager_feedback", [column])


def downgrade() -> None:
    op.drop_table("manager_feedback")
    op.drop_table("management_decisions")
    op.drop_table("management_risks")
    op.drop_table("dependency_edges")
    op.drop_index(op.f("ix_conversation_questions_status"), table_name="conversation_questions")
    op.drop_index(op.f("ix_conversation_questions_related_commitment_id"), table_name="conversation_questions")
    op.drop_index(op.f("ix_conversation_questions_asked_to_employee_id"), table_name="conversation_questions")
    op.drop_constraint(op.f("fk_conversation_questions_related_commitment_id_commitments"), "conversation_questions", type_="foreignkey")
    op.drop_constraint(op.f("fk_conversation_questions_asked_to_employee_id_employees"), "conversation_questions", type_="foreignkey")
    op.drop_column("conversation_questions", "status")
    op.drop_column("conversation_questions", "related_commitment_id")
    op.drop_column("conversation_questions", "asked_to_employee_id")
    op.drop_column("conversation_questions", "expected_answer_type")
    op.drop_index(op.f("ix_commitments_source_message_id"), table_name="commitments")
    op.drop_constraint(op.f("fk_commitments_source_message_id_messages"), "commitments", type_="foreignkey")
    op.drop_column("commitments", "confidence")
    op.drop_column("commitments", "source_message_id")
