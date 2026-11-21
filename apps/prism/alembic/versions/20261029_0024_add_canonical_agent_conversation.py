"""Add canonical Prism conversation and persisted job scopes.

Revision ID: 20261029_0024
Revises: 20261028_0023
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261029_0024"
down_revision = "20261028_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_threads",
        sa.Column("is_canonical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_agent_threads_is_canonical", "agent_threads", ["is_canonical"])
    op.create_index(
        "uq_agent_threads_one_canonical",
        "agent_threads",
        ["is_canonical"],
        unique=True,
        postgresql_where=sa.text("is_canonical"),
    )
    op.add_column(
        "agent_jobs",
        sa.Column("scope_mode", sa.String(length=32), server_default="chat", nullable=False),
    )
    op.add_column(
        "agent_jobs",
        sa.Column(
            "requested_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_jobs_scope_mode", "agent_jobs", ["scope_mode"])
    op.create_table(
        "agent_thread_aliases",
        sa.Column("legacy_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["canonical_thread_id"], ["agent_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("legacy_thread_id"),
    )
    op.create_index(
        "ix_agent_thread_aliases_canonical_thread_id",
        "agent_thread_aliases",
        ["canonical_thread_id"],
    )
    op.create_table(
        "agent_job_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("label", sa.String(length=255)),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selection_reason", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["job_id"], ["agent_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "source_kind", "external_id"),
    )
    op.create_index("ix_agent_job_sources_job_id", "agent_job_sources", ["job_id"])
    op.create_index("ix_agent_job_sources_external_id", "agent_job_sources", ["external_id"])

    connection = op.get_bind()
    threads = list(
        connection.execute(
            sa.text("SELECT id FROM agent_threads ORDER BY created_at, id")
        ).scalars()
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO agent_job_sources
                (id, job_id, source_kind, external_id, label, source_metadata,
                 selection_reason, created_at, updated_at)
            SELECT gen_random_uuid(), id, source_kind, source_external_id, source_label,
                   source_metadata, 'legacy_selected', now(), now()
            FROM agent_jobs
            WHERE source_kind IS NOT NULL AND source_external_id IS NOT NULL
            """
        )
    )
    if threads:
        canonical_id = threads[0]
        connection.execute(
            sa.text(
                "UPDATE agent_threads SET is_canonical=true, title='Prism', updated_at=now() WHERE id=:id"
            ),
            {"id": canonical_id},
        )
        for legacy_id in threads:
            connection.execute(
                sa.text(
                    "INSERT INTO agent_thread_aliases (legacy_thread_id, canonical_thread_id, created_at, updated_at) VALUES (:legacy, :canonical, now(), now())"
                ),
                {"legacy": legacy_id, "canonical": canonical_id},
            )
        if len(threads) > 1:
            legacy_ids = tuple(threads[1:])
            for table in ("agent_jobs", "agent_thread_messages"):
                connection.execute(
                    sa.text(
                        f"UPDATE {table} SET thread_id=:canonical WHERE thread_id IN :legacy"
                    ).bindparams(sa.bindparam("legacy", expanding=True)),
                    {"canonical": canonical_id, "legacy": legacy_ids},
                )
            connection.execute(
                sa.text(
                    "UPDATE agent_preferences SET source_thread_id=:canonical WHERE source_thread_id IN :legacy"
                ).bindparams(sa.bindparam("legacy", expanding=True)),
                {"canonical": canonical_id, "legacy": legacy_ids},
            )
            connection.execute(
                sa.text("DELETE FROM agent_threads WHERE id IN :legacy").bindparams(
                    sa.bindparam("legacy", expanding=True)
                ),
                {"legacy": legacy_ids},
            )


def downgrade() -> None:
    op.drop_table("agent_job_sources")
    op.drop_table("agent_thread_aliases")
    op.drop_index("ix_agent_jobs_scope_mode", table_name="agent_jobs")
    op.drop_column("agent_jobs", "requested_scope")
    op.drop_column("agent_jobs", "scope_mode")
    op.drop_index("uq_agent_threads_one_canonical", table_name="agent_threads")
    op.drop_index("ix_agent_threads_is_canonical", table_name="agent_threads")
    op.drop_column("agent_threads", "is_canonical")
