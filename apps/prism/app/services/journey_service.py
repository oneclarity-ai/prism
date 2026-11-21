"""Read-only reconstruction of a blocker journey from the audit records."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.agent_run import AgentRun
from app.models.blocker import Blocker
from app.models.employee import Employee
from app.models.message import Message
from app.schemas.journey import JourneyCommitmentRead, JourneyEventRead, JourneyRead


class JourneyService:
    """Build human-readable chains without inventing a second source of truth."""

    @staticmethod
    def list(db: Session, *, limit: int) -> list[JourneyRead]:
        blockers = list(
            db.scalars(
                select(Blocker)
                .join(Employee, Employee.id == Blocker.blocked_employee_id)
                .where(Employee.is_active.is_(True))
                .options(
                    selectinload(Blocker.blocked_employee),
                    selectinload(Blocker.dependency_owner),
                    selectinload(Blocker.commitments),
                )
                .order_by(Blocker.updated_at.desc(), Blocker.created_at.desc())
                .limit(limit)
            )
        )
        if not blockers:
            return []

        blocker_ids = [blocker.id for blocker in blockers]
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.blocker_id.in_(blocker_ids))
                .options(
                    selectinload(AgentRun.inbound_message),
                    selectinload(AgentRun.source_reply_message),
                    selectinload(AgentRun.dependency_message),
                )
                .order_by(AgentRun.created_at.asc())
            )
        )
        runs_by_blocker: dict[object, list[AgentRun]] = {}
        for run in runs:
            if run.blocker_id is not None:
                runs_by_blocker.setdefault(run.blocker_id, []).append(run)

        return [
            JourneyService._build(blocker, runs_by_blocker.get(blocker.id, []))
            for blocker in blockers
        ]

    @staticmethod
    def _build(blocker: Blocker, runs: list[AgentRun]) -> JourneyRead:
        events: list[JourneyEventRead] = []
        seen_message_ids: set[object] = set()
        blocked_name = JourneyService._first_name(blocker.blocked_employee.name)
        owner_name = (
            JourneyService._first_name(blocker.dependency_owner.name)
            if blocker.dependency_owner is not None
            else None
        )

        for run in runs:
            JourneyService._add_inbound_event(
                events, seen_message_ids, run.inbound_message, blocker, blocked_name, owner_name
            )
            JourneyService._add_outbound_event(
                events,
                seen_message_ids,
                run.source_reply_message,
                blocker,
                blocked_name,
                owner_name,
                purpose="update",
            )
            JourneyService._add_outbound_event(
                events,
                seen_message_ids,
                run.dependency_message,
                blocker,
                blocked_name,
                owner_name,
                purpose="dependency",
            )

        if not events:
            events.append(
                JourneyEventRead(
                    event_type="recorded",
                    title="Blocker recorded",
                    detail=blocker.description,
                    occurred_at=blocker.created_at,
                    employee_id=blocker.blocked_employee_id,
                )
            )

        commitments = [
            JourneyCommitmentRead(
                id=commitment.id,
                owner_name=JourneyService._first_name(commitment.employee.name),
                description=commitment.description,
                deadline=commitment.deadline,
                status=commitment.status,
            )
            for commitment in sorted(blocker.commitments, key=lambda item: item.created_at)
        ]
        for commitment in commitments:
            stored = next(item for item in blocker.commitments if item.id == commitment.id)
            events.append(
                JourneyEventRead(
                    event_type="commitment",
                    title="{} made a commitment".format(commitment.owner_name),
                    detail="{} · Due {}".format(
                        commitment.description, commitment.deadline.isoformat()
                    ),
                    occurred_at=stored.created_at,
                    employee_id=stored.employee_id,
                )
            )

        if blocker.resolved_at is not None:
            events.append(
                JourneyEventRead(
                    event_type="resolved",
                    title="Blocker resolved",
                    detail=(
                        "{} confirmed the dependency was delivered.".format(owner_name)
                        if owner_name
                        else "The dependency was marked as resolved."
                    ),
                    occurred_at=blocker.resolved_at,
                    employee_id=blocker.dependency_owner_id,
                )
            )

        events.sort(key=lambda item: item.occurred_at)
        last_activity_at = events[-1].occurred_at if events else blocker.updated_at
        return JourneyRead(
            blocker_id=blocker.id,
            title="{}'s blocker".format(blocked_name),
            description=blocker.description,
            status=blocker.status,
            severity=blocker.severity,
            blocked_employee_name=blocked_name,
            dependency_owner_name=owner_name,
            started_at=blocker.created_at,
            last_activity_at=last_activity_at,
            events=events,
            commitments=commitments,
        )

    @staticmethod
    def _add_inbound_event(
        events: list[JourneyEventRead],
        seen_message_ids: set[object],
        message: Optional[Message],
        blocker: Blocker,
        blocked_name: str,
        owner_name: Optional[str],
    ) -> None:
        if message is None or message.id in seen_message_ids:
            return
        seen_message_ids.add(message.id)
        sender_name = (
            JourneyService._first_name(message.employee.name) if message.employee else "Team member"
        )
        if message.employee_id == blocker.blocked_employee_id:
            title, event_type = "{} raised the blocker".format(blocked_name), "raised"
        elif message.employee_id == blocker.dependency_owner_id:
            title, event_type = (
                "{} replied about the dependency".format(owner_name or sender_name),
                "dependency_reply",
            )
        else:
            title, event_type = "{} replied".format(sender_name), "reply"
        events.append(
            JourneyEventRead(
                event_type=event_type,
                title=title,
                detail=message.content,
                occurred_at=JourneyService._message_time(message),
                employee_id=message.employee_id,
                message_id=message.id,
            )
        )

    @staticmethod
    def _add_outbound_event(
        events: list[JourneyEventRead],
        seen_message_ids: set[object],
        message: Optional[Message],
        blocker: Blocker,
        blocked_name: str,
        owner_name: Optional[str],
        *,
        purpose: str,
    ) -> None:
        if message is None or message.id in seen_message_ids:
            return
        seen_message_ids.add(message.id)
        recipient_name = (
            JourneyService._first_name(message.employee.name) if message.employee else "team member"
        )
        if message.employee_id == blocker.dependency_owner_id and purpose == "dependency":
            if "recorded" in message.content.casefold() and "eta" in message.content.casefold():
                title, event_type = (
                    "Agent recorded {}'s ETA".format(owner_name or recipient_name),
                    "agent_update",
                )
            else:
                title, event_type = (
                    "Agent asked {} for an ETA".format(owner_name or recipient_name),
                    "dependency_request",
                )
        elif message.employee_id == blocker.blocked_employee_id:
            title, event_type = "Agent updated {}".format(blocked_name), "agent_update"
        else:
            title, event_type = "Agent replied to {}".format(recipient_name), "agent_reply"
        events.append(
            JourneyEventRead(
                event_type=event_type,
                title=title,
                detail=message.content,
                occurred_at=JourneyService._message_time(message),
                employee_id=message.employee_id,
                message_id=message.id,
            )
        )

    @staticmethod
    def _message_time(message: Message) -> datetime:
        return message.external_created_at or message.created_at

    @staticmethod
    def _first_name(name: str) -> str:
        parts = " ".join((name or "").split()).split(" ")
        return parts[0] if parts and parts[0] else "Team member"
