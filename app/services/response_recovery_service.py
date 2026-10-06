"""Bounded recovery for inbound replies whose background processing did not finish."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.agents.management_agent import ManagementAgent
from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, MessageDirection
from app.models.message import Message


class ResponseRecoveryService:
    MAX_ATTEMPTS = 3
    STALE_PENDING_AFTER = timedelta(minutes=2)

    @staticmethod
    def process_due(db: Session, *, now: Optional[datetime] = None, limit: int = 10) -> int:
        current = now or datetime.now(timezone.utc)
        policy_version = get_settings().response_policy_version
        stale_before = current - ResponseRecoveryService.STALE_PENDING_AFTER
        message_ids = list(db.scalars(
            select(Message.id)
            .outerjoin(AgentRun, AgentRun.inbound_message_id == Message.id)
            .where(
                Message.direction == MessageDirection.INBOUND,
                or_(
                    AgentRun.id.is_(None),
                    and_(
                        or_(
                            AgentRun.attempt_count < ResponseRecoveryService.MAX_ATTEMPTS,
                            AgentRun.policy_version.is_(None),
                            AgentRun.policy_version != policy_version,
                        ),
                        or_(
                            and_(
                                AgentRun.status == AgentRunStatus.FAILED,
                                AgentRun.next_retry_at.is_not(None),
                                AgentRun.next_retry_at <= current,
                            ),
                            and_(
                                AgentRun.status == AgentRunStatus.FAILED,
                                or_(
                                    AgentRun.policy_version.is_(None),
                                    AgentRun.policy_version != policy_version,
                                ),
                            ),
                            and_(
                                AgentRun.status == AgentRunStatus.PENDING,
                                AgentRun.last_attempt_at.is_not(None),
                                AgentRun.last_attempt_at <= stale_before,
                            ),
                        ),
                    ),
                ),
            )
            .order_by(Message.created_at, Message.id)
            .limit(limit)
        ))
        processed = 0
        for message_id in message_ids:
            result = ManagementAgent.process_message(db, str(message_id))
            if result is not None:
                processed += 1
        return processed
