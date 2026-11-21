"""Persist Prism roles, departments, and reporting relationships.

Revision ID: 20261120_0045
Revises: 20261104_0044
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261120_0045"
down_revision = "20261104_0044"
branch_labels = None
depends_on = None


def _classify(name: str, description: str) -> tuple[str, str]:
    # Frozen migration rules: later application changes must not change this backfill.
    groups = [
        (("chief of staff",), "Chief of Staff", "Leadership"),
        (
            ("market research", "marketing", "content", "brand"),
            "Market Research Analyst",
            "Marketing",
        ),
        (("sales", "outreach", "leads"), "Sales Outreach Specialist", "Sales"),
        (("customer", "client success"), "Customer Intelligence Analyst", "Customer Success"),
        (("qa", "quality", "tester", "testing"), "QA Analyst", "Quality Assurance"),
        (
            ("deployment", "devops", "release", "engineering"),
            "Deployment & Engineering Specialist",
            "Engineering",
        ),
        (("research", "ai ml", "machine learning"), "AI Researcher", "Research & Development"),
        (("finance", "accounting", "budget"), "Finance Analyst", "Finance"),
        (("recruit", "human resources", "people ops"), "People Operations Specialist", "People"),
        (("email", "inbox"), "Inbox Assistant", "Operations"),
        (("delivery", "project"), "Delivery Coordinator", "Operations"),
        (("team manager",), "Team Manager", "Operations"),
        (("executive", "assistant"), "Executive Assistant", "Operations"),
    ]
    for value in (name.casefold(), description.casefold()):
        for terms, role, department in groups:
            if any(term in value for term in terms):
                return role, department
    return "Prism Specialist", "Operations"


def upgrade() -> None:
    op.add_column(
        "prisms",
        sa.Column("job_role", sa.String(120), nullable=False, server_default="Prism Specialist"),
    )
    op.add_column(
        "prisms",
        sa.Column("department", sa.String(100), nullable=False, server_default="Operations"),
    )
    op.add_column("prisms", sa.Column("reports_to_prism_id", postgresql.UUID(as_uuid=True)))
    op.add_column(
        "prisms",
        sa.Column("is_chief_of_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_prisms_reports_to_prism_id_prisms",
        "prisms",
        "prisms",
        ["reports_to_prism_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "no_self_reporting", "prisms", "reports_to_prism_id IS NULL OR reports_to_prism_id <> id"
    )
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT id, name, description, template_key, state FROM prisms ORDER BY created_at, id"
            )
        ).mappings()
    )
    chief = next(
        (
            row
            for row in rows
            if row["state"] != "ARCHIVED"
            and " ".join(row["name"].casefold().split()) == "chief of staff"
        ),
        None,
    )
    if chief is None:
        chief = next(
            (
                row
                for row in rows
                if row["state"] != "ARCHIVED" and row["template_key"] == "executive_assistant"
            ),
            None,
        )
    for row in rows:
        role, department = _classify(row["name"], row["description"])
        is_chief = chief is not None and row["id"] == chief["id"]
        bind.execute(
            sa.text(
                "UPDATE prisms SET job_role=:role, department=:department, is_chief_of_staff=:chief, reports_to_prism_id=:manager WHERE id=:id"
            ),
            {
                "id": row["id"],
                "role": "Chief of Staff" if is_chief else role,
                "department": "Leadership" if is_chief else department,
                "chief": is_chief,
                "manager": chief["id"]
                if chief and not is_chief and row["state"] != "ARCHIVED"
                else None,
            },
        )
    op.create_index(
        "uq_prisms_chief_of_staff",
        "prisms",
        ["is_chief_of_staff"],
        unique=True,
        postgresql_where=sa.text("is_chief_of_staff AND state <> 'ARCHIVED'"),
    )
    op.create_index("ix_prisms_reports_to_prism_id", "prisms", ["reports_to_prism_id"])


def downgrade() -> None:
    op.drop_index("ix_prisms_reports_to_prism_id", table_name="prisms")
    op.drop_index("uq_prisms_chief_of_staff", table_name="prisms")
    op.drop_constraint(op.f("ck_prisms_no_self_reporting"), "prisms", type_="check")
    op.drop_constraint("fk_prisms_reports_to_prism_id_prisms", "prisms", type_="foreignkey")
    for column in ("is_chief_of_staff", "reports_to_prism_id", "department", "job_role"):
        op.drop_column("prisms", column)
