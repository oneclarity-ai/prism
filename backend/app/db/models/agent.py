import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.enums import AgentStatus


class Agent(IdMixin, TimestampMixin, Base):
    """One agent "employee". Behaviour is data: instructions, model, runtime and tool grants."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_agents_org_key"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    runtime: Mapped[str] = mapped_column(String(64), default="openai_agents")
    # Azure OpenAI deployment name; empty means use AZURE_OPENAI_DEPLOYMENT.
    model: Mapped[str] = mapped_column(String(200), default="")
    tool_grants: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default=AgentStatus.active)
    max_turns: Mapped[int] = mapped_column(default=80)
    run_budget_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("3.00"))
    monthly_budget_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("100.00"))
    reports_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
