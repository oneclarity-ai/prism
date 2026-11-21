"""Add provenance for Teams drafts prepared from Prism observations.

Revision ID: 20261030_0037
Revises: 20261030_0036
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0037"
down_revision = "20261030_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prism_observation_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agreement_revision", sa.Integer(), nullable=False),
        sa.Column("destination_external_id", sa.String(length=512), nullable=False),
        sa.Column("evidence_event_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["prism_id"], ["prisms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["prism_observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        sa.UniqueConstraint("observation_id", "request_id"),
    )
    op.create_index("ix_prism_observation_drafts_prism_id", "prism_observation_drafts", ["prism_id"])
    op.create_index("ix_prism_observation_drafts_observation_id", "prism_observation_drafts", ["observation_id"])


def downgrade() -> None:
    op.drop_index("ix_prism_observation_drafts_observation_id", table_name="prism_observation_drafts")
    op.drop_index("ix_prism_observation_drafts_prism_id", table_name="prism_observation_drafts")
    op.drop_table("prism_observation_drafts")
