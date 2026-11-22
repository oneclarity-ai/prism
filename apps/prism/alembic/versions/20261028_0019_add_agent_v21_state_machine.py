"""Add durable Prism v2.1 agent state machine.

Revision ID: 20261028_0019
Revises: 20261028_0018
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0019"
down_revision = "20261028_0018"
branch_labels = None
depends_on = None

job_state = postgresql.ENUM(
    "QUEUED",
    "RESEARCHING",
    "PLANNING",
    "WAITING_FOR_APPROVAL",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    name="agent_job_state",
    create_type=False,
)
step_state = postgresql.ENUM(
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    name="agent_step_state",
    create_type=False,
)
proposal_state = postgresql.ENUM(
    "DRAFT",
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "EXECUTING",
    "EXECUTED",
    "FAILED",
    name="action_proposal_state",
    create_type=False,
)
approval_type = postgresql.ENUM(
    "APPROVED", "REJECTED", name="approval_decision_type", create_type=False
)
execution_state = postgresql.ENUM(
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "UNCERTAIN",
    name="tool_execution_state",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    job_state.create(bind, checkfirst=True)
    step_state.create(bind, checkfirst=True)
    proposal_state.create(bind, checkfirst=True)
    approval_type.create(bind, checkfirst=True)
    execution_state.create(bind, checkfirst=True)

    op.create_table(
        "agent_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_kind", sa.String(length=40)),
        sa.Column("source_external_id", sa.String(length=512)),
        sa.Column("source_label", sa.String(length=255)),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_threads")),
    )
    op.create_index(
        op.f("ix_agent_threads_source_external_id"), "agent_threads", ["source_external_id"]
    )

    op.create_table(
        "agent_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("state", job_state, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("safe_error_code", sa.String(length=80)),
        sa.Column("safe_error_detail", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["agent_threads.id"],
            ondelete="CASCADE",
            name=op.f("fk_agent_jobs_thread_id_agent_threads"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_jobs")),
    )
    op.create_index(op.f("ix_agent_jobs_thread_id"), "agent_jobs", ["thread_id"])
    op.create_index(op.f("ix_agent_jobs_state"), "agent_jobs", ["state"])

    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("state", step_state, nullable=False),
        sa.Column("safe_error_code", sa.String(length=80)),
        sa.Column("safe_error_detail", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_agent_steps_job_id_agent_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
        sa.UniqueConstraint("job_id", "sequence", name=op.f("uq_agent_steps_job_id")),
    )
    op.create_index(op.f("ix_agent_steps_job_id"), "agent_steps", ["job_id"])

    op.create_table(
        "action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("logical_action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("state", proposal_state, nullable=False),
        sa.Column("destination", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=71), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_action_proposals_job_id_agent_jobs"),
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id"],
            ["action_proposals.id"],
            ondelete="RESTRICT",
            name=op.f("fk_action_proposals_previous_revision_id_action_proposals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_proposals")),
        sa.UniqueConstraint(
            "logical_action_id", "revision", name=op.f("uq_action_proposals_logical_action_id")
        ),
    )
    op.create_index(op.f("ix_action_proposals_job_id"), "action_proposals", ["job_id"])
    op.create_index(
        op.f("ix_action_proposals_logical_action_id"), "action_proposals", ["logical_action_id"]
    )
    op.create_index(op.f("ix_action_proposals_payload_hash"), "action_proposals", ["payload_hash"])
    op.create_index(op.f("ix_action_proposals_state"), "action_proposals", ["state"])

    op.create_table(
        "approval_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", approval_type, nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=71), nullable=False),
        sa.Column("manager_identity", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["action_proposals.id"],
            ondelete="CASCADE",
            name=op.f("fk_approval_decisions_proposal_id_action_proposals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_decisions")),
        sa.UniqueConstraint("proposal_id", name=op.f("uq_approval_decisions_proposal_id")),
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("state", execution_state, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=71)),
        sa.Column("safe_result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("safe_error_code", sa.String(length=80)),
        sa.Column("safe_error_detail", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_tool_executions_job_id_agent_jobs"),
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["action_proposals.id"],
            ondelete="RESTRICT",
            name=op.f("fk_tool_executions_proposal_id_action_proposals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_tool_executions_idempotency_key")),
    )
    op.create_index(op.f("ix_tool_executions_job_id"), "tool_executions", ["job_id"])
    op.create_index(op.f("ix_tool_executions_proposal_id"), "tool_executions", ["proposal_id"])
    op.create_index(op.f("ix_tool_executions_state"), "tool_executions", ["state"])


def downgrade() -> None:
    op.drop_table("tool_executions")
    op.drop_table("approval_decisions")
    op.drop_table("action_proposals")
    op.drop_table("agent_steps")
    op.drop_table("agent_jobs")
    op.drop_table("agent_threads")
    bind = op.get_bind()
    execution_state.drop(bind, checkfirst=True)
    approval_type.drop(bind, checkfirst=True)
    proposal_state.drop(bind, checkfirst=True)
    step_state.drop(bind, checkfirst=True)
    job_state.drop(bind, checkfirst=True)
