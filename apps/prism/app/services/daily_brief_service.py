from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.employee import Employee
from app.models.enums import ActivityEventType, BlockerStatus, CommitmentStatus, TaskStatus
from app.models.intelligence import ManagementRisk
from app.models.memory import ActivityEvent
from app.models.task import Task
from app.schemas.intelligence import DailyBrief


class DailyBriefService:
    @staticmethod
    def build(db: Session, *, as_of: datetime | None = None) -> DailyBrief:
        now = as_of or datetime.now(timezone.utc)
        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo or timezone.utc)
        events = list(
            db.scalars(
                select(ActivityEvent)
                .where(
                    ActivityEvent.occurred_at >= start,
                    ActivityEvent.occurred_at <= now,
                )
                .order_by(ActivityEvent.occurred_at)
            )
        )
        managed_ids = set(db.scalars(select(Employee.id).where(Employee.is_managed.is_(True))))

        def event_lines(event_type: ActivityEventType, label: str) -> list[str]:
            return [
                f"{label}: {event.entity_type} {event.entity_id}"
                for event in events
                if event.event_type == event_type
            ]

        in_progress = (
            [
                f"{task.owner.name}: {task.title}"
                for task in db.scalars(
                    select(Task)
                    .where(Task.owner_id.in_(managed_ids), Task.status == TaskStatus.IN_PROGRESS)
                    .limit(20)
                )
            ]
            if managed_ids
            else []
        )
        missed = (
            [
                f"{item.employee.name}: {item.description} (due {item.deadline.isoformat()})"
                for item in db.scalars(
                    select(Commitment).where(
                        Commitment.employee_id.in_(managed_ids),
                        Commitment.status == CommitmentStatus.MISSED,
                    )
                )
            ]
            if managed_ids
            else []
        )
        risks = list(db.scalars(select(ManagementRisk).where(ManagementRisk.status == "active")))
        waiting = (
            [
                f"{item.blocked_employee.name} is waiting on "
                + ", ".join(
                    owner.name
                    for owner in [
                        dependency.employee
                        for dependency in item.dependencies
                        if dependency.is_active
                    ]
                )
                for item in db.scalars(
                    select(Blocker).where(
                        Blocker.blocked_employee_id.in_(managed_ids),
                        Blocker.status == BlockerStatus.OPEN,
                    )
                )
            ]
            if managed_ids
            else []
        )
        changed_etas = event_lines(ActivityEventType.COMMITMENT_REVISED, "Revised commitment")
        completed = event_lines(ActivityEventType.COMMITMENT_COMPLETED, "Completed")
        completed += event_lines(ActivityEventType.TASK_STATUS_CHANGED, "Task changed")
        important = [
            event.event_type.value.replace("_", " ")
            for event in events
            if event.event_type
            in {
                ActivityEventType.BLOCKER_DEPENDENCY_OWNER_CHANGED,
                ActivityEventType.TASK_DEADLINE_CHANGED,
                ActivityEventType.PROJECT_TARGET_DATE_CHANGED,
            }
        ]
        normal_count = max(
            0,
            len(in_progress)
            - len([risk for risk in risks if risk.severity in {"attention", "urgent"}]),
        )
        return DailyBrief(
            date=now.date(),
            completed=completed,
            in_progress=in_progress,
            new_blockers=event_lines(ActivityEventType.BLOCKER_CREATED, "New blocker"),
            resolved_blockers=event_lines(ActivityEventType.BLOCKER_RESOLVED, "Resolved blocker"),
            missed_commitments=missed,
            changed_etas=changed_etas,
            dependencies_at_risk=[
                risk.summary for risk in risks if risk.severity in {"attention", "urgent"}
            ],
            people_waiting=waiting,
            needs_attention=[
                risk.summary for risk in risks if risk.severity in {"attention", "urgent"}
            ],
            important_changes=important,
            no_action_required=(
                [
                    f"{normal_count} active work item(s) progressing without an attention-level signal"
                ]
                if normal_count
                else []
            ),
        )
