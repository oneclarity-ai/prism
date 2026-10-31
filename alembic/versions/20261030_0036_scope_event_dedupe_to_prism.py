"""Scope Teams event de-duplication to each Prism.

Two Prisms reading the same chat each need their own copy of an event; a global unique key made
the second Prism skip every message the first had stored.

Revision ID: 20261030_0036
Revises: 20261030_0035
Create Date: 2026-10-30
"""

from alembic import op

revision = "20261030_0036"
down_revision = "20261030_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_prism_external_events_dedupe_key", "prism_external_events", type_="unique")
    op.create_unique_constraint(
        "uq_prism_external_events_prism_dedupe",
        "prism_external_events",
        ["prism_id", "dedupe_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_prism_external_events_prism_dedupe", "prism_external_events", type_="unique")
    op.create_unique_constraint(
        "uq_prism_external_events_dedupe_key", "prism_external_events", ["dedupe_key"]
    )
