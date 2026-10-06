"""Ephemeral development fixtures that never enter operational tables."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import BlockerSeverity, BlockerStatus, CommitmentStatus
from app.schemas.development import DummyJourneyResult
from app.schemas.journey import JourneyCommitmentRead, JourneyEventRead, JourneyRead
from app.services.errors import RuleViolationError


class DevelopmentService:
    """Build a harmless in-memory Journey preview without database writes."""

    DUMMY_MARKER = "DUMMY TEST — Status API changes needed for connector updates"

    @staticmethod
    def create_dummy_journey(db: Session) -> DummyJourneyResult:
        if get_settings().app_env.casefold() != "development":
            raise RuleViolationError("The dummy Journey flow is available only in development")

        # Keep stable identifiers for UI rendering while creating no employee,
        # message, blocker, commitment, memory, or agent-run rows.
        blocker_id = uuid.uuid5(uuid.NAMESPACE_URL, "personal-agent/dummy-journey/blocker")
        commitment_id = uuid.uuid5(uuid.NAMESPACE_URL, "personal-agent/dummy-journey/commitment")
        now = datetime.now(timezone.utc)
        events = [
            JourneyEventRead(
                event_type="raised",
                title="Jambu raised the blocker",
                detail="[Preview] Connector updates need the Status API changes.",
                occurred_at=now,
            ),
            JourneyEventRead(
                event_type="dependency_request",
                title="Agent asked Shubham for an ETA",
                detail="[Preview] When do you expect the Status API changes to be ready?",
                occurred_at=now + timedelta(seconds=1),
            ),
            JourneyEventRead(
                event_type="dependency_reply",
                title="Shubham replied about the dependency",
                detail="[Preview] I will share the changes by 6 PM IST.",
                occurred_at=now + timedelta(seconds=2),
            ),
            JourneyEventRead(
                event_type="resolved",
                title="Blocker resolved",
                detail="[Preview] Shubham confirmed the changes were shared.",
                occurred_at=now + timedelta(seconds=3),
            ),
        ]
        commitment = JourneyCommitmentRead(
            id=commitment_id,
            owner_name="Shubham",
            description="[Preview] Provide the Status API changes",
            deadline=now + timedelta(hours=2),
            status=CommitmentStatus.COMPLETED,
        )
        journey = JourneyRead(
            blocker_id=blocker_id,
            title="Jambu's preview blocker",
            description=DevelopmentService.DUMMY_MARKER,
            status=BlockerStatus.RESOLVED,
            severity=BlockerSeverity.MEDIUM,
            blocked_employee_name="Jambu",
            dependency_owner_name="Shubham",
            started_at=now,
            last_activity_at=now + timedelta(seconds=3),
            events=events,
            commitments=[commitment],
        )
        return DummyJourneyResult(
            created=True,
            blocker_id=blocker_id,
            message="Created an ephemeral Journey preview. No database, Teams, or Azure records were written.",
            journey=journey,
        )
