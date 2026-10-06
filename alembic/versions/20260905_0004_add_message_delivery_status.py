"""add message delivery status

Revision ID: 20260905_0004
Revises: 20260905_0003
Create Date: 2026-09-05 00:00:03

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260905_0004"
down_revision: Union[str, Sequence[str], None] = "20260905_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    message_delivery_status = sa.Enum("RECORDED", "DELIVERED", "FAILED", name="message_delivery_status")
    message_delivery_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "messages",
        sa.Column(
            "delivery_status",
            message_delivery_status,
            server_default="RECORDED",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_messages_delivery_status"), "messages", ["delivery_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_delivery_status"), table_name="messages")
    op.drop_column("messages", "delivery_status")
    sa.Enum(name="message_delivery_status").drop(op.get_bind(), checkfirst=True)
