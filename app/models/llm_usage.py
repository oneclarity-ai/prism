from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="azure_openai")
    model: Mapped[str] = mapped_column(String(255), index=True)
    deployment: Mapped[str] = mapped_column(String(255))
    feature: Mapped[str] = mapped_column(String(80), index=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cached_input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_input_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 10))
    estimated_output_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 10))
    estimated_total_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 10))
    pricing_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    request_id: Mapped[Optional[str]] = mapped_column(String(255))
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
