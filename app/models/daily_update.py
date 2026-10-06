from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.employee import Employee


class DailyUpdate(TimestampMixin, Base):
    __tablename__ = "daily_updates"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "update_date", name="uq_daily_updates_employee_daily_update"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    update_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    completed_summary: Mapped[Optional[str]] = mapped_column(Text)
    today_summary: Mapped[Optional[str]] = mapped_column(Text)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    blocker_summary: Mapped[Optional[str]] = mapped_column(Text)
    raw_message: Mapped[Optional[str]] = mapped_column(Text)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="daily_updates")
