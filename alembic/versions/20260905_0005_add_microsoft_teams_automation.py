"""add Microsoft Teams automation foundation

Revision ID: 20260905_0005
Revises: 20260905_0004
Create Date: 2026-09-05 00:00:05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260905_0005"
down_revision: Union[str, Sequence[str], None] = "20260905_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL named enums are created explicitly below.  `create_type=False`
    # prevents create_table from trying to create the same enum a second time.
    automation_status = postgresql.ENUM(
        "RUNNING", "STOPPED", "FAILED", name="automation_status", create_type=False
    )
    microsoft_subscription_status = postgresql.ENUM(
        "ACTIVE",
        "STOPPED",
        "EXPIRED",
        "FAILED",
        name="microsoft_subscription_status",
        create_type=False,
    )
    automation_status.create(op.get_bind(), checkfirst=True)
    microsoft_subscription_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "employees",
        sa.Column("is_managed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(op.f("ix_employees_is_managed"), "employees", ["is_managed"], unique=False)
    op.add_column("messages", sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_messages_external_created_at"), "messages", ["external_created_at"], unique=False
    )

    op.create_table(
        "microsoft_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("microsoft_user_id", sa.String(length=255), nullable=False),
        sa.Column("user_principal_name", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
        sa.UniqueConstraint("microsoft_user_id"),
    )
    op.create_index(
        op.f("ix_microsoft_connections_tenant_id"), "microsoft_connections", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_microsoft_connections_microsoft_user_id"),
        "microsoft_connections",
        ["microsoft_user_id"],
        unique=False,
    )

    op.create_table(
        "microsoft_oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(
        op.f("ix_microsoft_oauth_states_state_hash"), "microsoft_oauth_states", ["state_hash"], unique=False
    )
    op.create_index(
        op.f("ix_microsoft_oauth_states_expires_at"), "microsoft_oauth_states", ["expires_at"], unique=False
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", automation_status, nullable=False),
        sa.Column("initial_prompt", sa.Text(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("delivered_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["microsoft_connections.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_automation_runs_connection_id"), "automation_runs", ["connection_id"], unique=False)
    op.create_index(op.f("ix_automation_runs_status"), "automation_runs", ["status"], unique=False)

    op.create_table(
        "microsoft_teams_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        sa.Column("encrypted_client_state", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", microsoft_subscription_status, nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["automation_run_id"], ["automation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["connection_id"], ["microsoft_connections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_subscription_id"),
    )
    op.create_index(
        op.f("ix_microsoft_teams_subscriptions_connection_id"),
        "microsoft_teams_subscriptions",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_microsoft_teams_subscriptions_automation_run_id"),
        "microsoft_teams_subscriptions",
        ["automation_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_microsoft_teams_subscriptions_conversation_id"),
        "microsoft_teams_subscriptions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_microsoft_teams_subscriptions_expires_at"),
        "microsoft_teams_subscriptions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_microsoft_teams_subscriptions_status"),
        "microsoft_teams_subscriptions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_microsoft_teams_subscriptions_status"), table_name="microsoft_teams_subscriptions")
    op.drop_index(op.f("ix_microsoft_teams_subscriptions_expires_at"), table_name="microsoft_teams_subscriptions")
    op.drop_index(op.f("ix_microsoft_teams_subscriptions_conversation_id"), table_name="microsoft_teams_subscriptions")
    op.drop_index(op.f("ix_microsoft_teams_subscriptions_automation_run_id"), table_name="microsoft_teams_subscriptions")
    op.drop_index(op.f("ix_microsoft_teams_subscriptions_connection_id"), table_name="microsoft_teams_subscriptions")
    op.drop_table("microsoft_teams_subscriptions")
    op.drop_index(op.f("ix_automation_runs_status"), table_name="automation_runs")
    op.drop_index(op.f("ix_automation_runs_connection_id"), table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index(op.f("ix_microsoft_oauth_states_expires_at"), table_name="microsoft_oauth_states")
    op.drop_index(op.f("ix_microsoft_oauth_states_state_hash"), table_name="microsoft_oauth_states")
    op.drop_table("microsoft_oauth_states")
    op.drop_index(op.f("ix_microsoft_connections_microsoft_user_id"), table_name="microsoft_connections")
    op.drop_index(op.f("ix_microsoft_connections_tenant_id"), table_name="microsoft_connections")
    op.drop_table("microsoft_connections")
    op.drop_index(op.f("ix_messages_external_created_at"), table_name="messages")
    op.drop_column("messages", "external_created_at")
    op.drop_index(op.f("ix_employees_is_managed"), table_name="employees")
    op.drop_column("employees", "is_managed")
    sa.Enum(name="microsoft_subscription_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="automation_status").drop(op.get_bind(), checkfirst=True)
