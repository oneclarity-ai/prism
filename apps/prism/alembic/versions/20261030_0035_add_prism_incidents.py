"""Add conservative cross-Prism incident links and their audit trail.

Revision ID: 20261030_0035
Revises: 20261030_0034
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261030_0035"
down_revision = "20261030_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prism_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "prism_incident_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prism_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["prism_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["prism_observations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prism_incident_events_incident_id", "prism_incident_events", ["incident_id"])
    op.add_column("prism_observations", sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("prism_observations", sa.Column("evidence_key", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_prism_observations_incident_id",
        "prism_observations",
        "prism_incidents",
        ["incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_prism_observations_incident_id", "prism_observations", ["incident_id"])
    op.create_index("ix_prism_observations_evidence_key", "prism_observations", ["evidence_key"])


def downgrade() -> None:
    op.drop_index("ix_prism_observations_evidence_key", table_name="prism_observations")
    op.drop_index("ix_prism_observations_incident_id", table_name="prism_observations")
    op.drop_constraint("fk_prism_observations_incident_id", "prism_observations", type_="foreignkey")
    op.drop_column("prism_observations", "evidence_key")
    op.drop_column("prism_observations", "incident_id")
    op.drop_index("ix_prism_incident_events_incident_id", table_name="prism_incident_events")
    op.drop_table("prism_incident_events")
    op.drop_table("prism_incidents")
