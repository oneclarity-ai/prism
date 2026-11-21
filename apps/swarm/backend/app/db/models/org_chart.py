import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class OrgPosition(IdMixin, TimestampMixin, Base):
    """A seat in the org chart (CEO, CTO, QA Manager…). Held by a person, an agent, or vacant."""

    __tablename__ = "org_positions"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_positions.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(
        String(32), default="member"
    )  # ceo | executive | senior_manager | manager | member
    department: Mapped[str] = mapped_column(String(100), default="Leadership")
    holder_type: Mapped[str] = mapped_column(String(16), default="vacant")  # vacant | human | agent
    holder_name: Mapped[str] = mapped_column(String(200), default="")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    planned_agent_key: Mapped[str | None] = mapped_column(String(64))  # from app/agents catalog, for vacant agent seats
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(default=0)
