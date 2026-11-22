"""Random public Prism codes with reversible legacy aliases.

Revision ID: 20261122_0050
Revises: 20261122_0049
"""

import sqlalchemy as sa

from alembic import op

revision = "20261122_0050"
down_revision = "20261122_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep sequential aliases for existing bookmarks and for exact rollback to 0049.
    op.add_column("prisms", sa.Column("legacy_code", sa.String(24), nullable=True))
    op.execute("UPDATE prisms SET legacy_code = code")
    op.alter_column(
        "prisms",
        "legacy_code",
        nullable=False,
        server_default=sa.text("'PR-' || nextval('prism_code_seq')::text"),
    )
    op.create_unique_constraint("uq_prisms_legacy_code", "prisms", ["legacy_code"])
    op.execute("""
        CREATE FUNCTION prism_next_code() RETURNS text
        LANGUAGE plpgsql VOLATILE AS $$
        DECLARE
            alphabet constant text := 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
            entropy bytea;
            candidate text;
            attempt integer;
            position integer;
        BEGIN
            -- Serialize allocation per schema so concurrent inserts can retry collisions
            -- before the unique constraint is reached. This is an identity, not a secret.
            PERFORM pg_advisory_xact_lock(hashtext(current_schema()), hashtext('prism_public_code'));
            FOR attempt IN 1..128 LOOP
                entropy := uuid_send(gen_random_uuid());
                candidate := 'p';
                FOR position IN 0..4 LOOP
                    candidate := candidate || substr(alphabet, (get_byte(entropy, position) % 62) + 1, 1);
                END LOOP;
                IF substring(candidate FROM 2) !~ '[A-Z]'
                   OR substring(candidate FROM 2) !~ '[a-z]'
                   OR substring(candidate FROM 2) !~ '[0-9]' THEN
                    CONTINUE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM prisms WHERE code = candidate) THEN
                    RETURN candidate;
                END IF;
            END LOOP;
            RAISE EXCEPTION 'Could not allocate a unique Prism code; try creating it again';
        END;
        $$
    """)
    op.execute("UPDATE prisms SET code = prism_next_code()")
    op.alter_column("prisms", "code", server_default=sa.text("prism_next_code()"))


def downgrade() -> None:
    op.execute("UPDATE prisms SET code = legacy_code")
    op.alter_column(
        "prisms", "code", server_default=sa.text("'PR-' || nextval('prism_code_seq')::text")
    )
    op.drop_constraint("uq_prisms_legacy_code", "prisms", type_="unique")
    op.drop_column("prisms", "legacy_code")
    op.execute("DROP FUNCTION prism_next_code()")
