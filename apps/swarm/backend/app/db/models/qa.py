import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.enums import ApprovalStatus, BugStatus, Severity, TestCaseStatus


class TestCase(IdMixin, TimestampMixin, Base):
    __tablename__ = "test_cases"
    __test__ = False  # not a pytest test class

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    given: Mapped[str] = mapped_column(Text, default="")
    when: Mapped[str] = mapped_column(Text, default="")
    then: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=TestCaseStatus.pending)
    evidence_artifact_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class BugDraft(IdMixin, TimestampMixin, Base):
    __tablename__ = "bug_drafts"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test_cases.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    steps: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    actual: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(32), default=Severity.medium)
    status: Mapped[str] = mapped_column(String(32), default=BugStatus.draft)
    external_url: Mapped[str | None] = mapped_column(String(2000))
    # Set by the merge step of a parallel run when another sub-agent reported the same bug.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bug_drafts.id", ondelete="SET NULL"))


class Approval(IdMixin, TimestampMixin, Base):
    """Ask-first gate: one row per tool call that needs a human decision."""

    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("org_id", "decision_key", name="uq_approvals_org_decision_key"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.pending, index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str] = mapped_column(Text, default="")
    decision_key: Mapped[str | None] = mapped_column(String(200))


class BudgetLedger(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_ledger"
    __table_args__ = (UniqueConstraint("run_id", name="uq_budget_ledger_run_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), default=Decimal("0"))
