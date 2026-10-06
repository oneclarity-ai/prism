"""Import and distribute a manager-authored deployment checklist."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.enums import MessageDirection, TaskStatus
from app.models.management_context import ManagementContext
from app.models.message import Message
from app.models.response_state import ConversationQuestion
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.errors import NotFoundError, RuleViolationError
from app.services.microsoft_service import MicrosoftService
from app.services.task_service import TaskService


@dataclass(frozen=True)
class DeploymentItem:
    title: str
    status: TaskStatus


class DeploymentListService:
    STATUS = {
        "DONE": TaskStatus.DONE,
        "IN PROGRESS": TaskStatus.IN_PROGRESS,
        "TO DO": TaskStatus.TODO,
    }
    ITEM_PATTERN = re.compile(
        r"^(?P<title>.+?)\s*\[\s*(?P<status>DONE|IN\s+PROGRESS|TO\s+DO)\s*\]\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def parse(content: str) -> dict[str, list[DeploymentItem]]:
        assignments: dict[str, list[DeploymentItem]] = {}
        owner: str | None = None
        for raw_line in content.replace("\xa0", " ").splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            match = DeploymentListService.ITEM_PATTERN.match(line)
            if match is None:
                owner = line
                assignments.setdefault(owner, [])
                continue
            if owner is None:
                raise RuleViolationError("Deployment list has a task before its owner heading")
            status_label = " ".join(match.group("status").upper().split())
            assignments[owner].append(
                DeploymentItem(
                    title=match.group("title").strip().rstrip("."),
                    status=DeploymentListService.STATUS[status_label],
                )
            )
        return {name: items for name, items in assignments.items() if items}

    @staticmethod
    def resolve_people(
        db: Session, assignments: dict[str, list[DeploymentItem]]
    ) -> dict[str, Employee]:
        employees = list(
            db.scalars(
                select(Employee).where(
                    Employee.is_active.is_(True), Employee.teams_user_id.is_not(None)
                )
            )
        )
        by_name = {" ".join(employee.name.casefold().split()): employee for employee in employees}
        resolved: dict[str, Employee] = {}
        missing = []
        for name in assignments:
            employee = by_name.get(" ".join(name.casefold().split()))
            if employee is None:
                missing.append(name)
            else:
                resolved[name] = employee
        if missing:
            raise RuleViolationError(
                "These deployment-list owners do not uniquely match active Teams users: "
                + ", ".join(missing)
            )
        return resolved

    @staticmethod
    def sync_tasks(
        db: Session,
        entry: ManagementContext,
        assignments: dict[str, list[DeploymentItem]],
        people: dict[str, Employee],
    ) -> int:
        marker = "Knowledge source: {} ({})".format(entry.title, entry.id)
        changed = 0
        for owner_name, items in assignments.items():
            employee = people[owner_name]
            for item in items:
                task = db.scalar(
                    select(Task).where(
                        Task.owner_id == employee.id,
                        func.lower(Task.title) == item.title.casefold(),
                        Task.description == marker,
                    )
                )
                if task is None:
                    TaskService.create(
                        db,
                        TaskCreate(
                            owner_id=employee.id,
                            title=item.title,
                            description=marker,
                            expected_outcome=item.title,
                            status=item.status,
                        ),
                        commit=False,
                    )
                    changed += 1
                elif task.status != item.status:
                    TaskService.update(db, task.id, TaskUpdate(status=item.status), commit=False)
                    changed += 1
        return changed

    @staticmethod
    def message_body(entry: ManagementContext, items: list[DeploymentItem]) -> str:
        open_items = [item for item in items if item.status != TaskStatus.DONE]
        completed = len(items) - len(open_items)
        lines = [entry.title]
        if open_items:
            lines.extend(["", "Your open items:"])
            lines.extend(
                "• {} [{}]".format(item.title, item.status.value.replace("_", " ").upper())
                for item in open_items
            )
            lines.extend(
                [
                    "",
                    "{} other item(s) are marked done.".format(completed),
                    "Please reply with the current status of each open item, any blockers or dependencies, and the ETA for what remains.",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "All {} assigned item(s) are marked done.".format(completed),
                    "Please confirm they are ready for deployment, or share anything still pending or blocked.",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def distribute(db: Session, entry_id: uuid.UUID) -> dict[str, object]:
        entry = db.scalar(
            select(ManagementContext).where(
                ManagementContext.id == entry_id, ManagementContext.is_active.is_(True)
            )
        )
        if entry is None:
            raise NotFoundError("Deployment list was not found")
        assignments = DeploymentListService.parse(entry.content)
        if not assignments:
            raise RuleViolationError("Deployment list has no valid owner/task assignments")
        people = DeploymentListService.resolve_people(db, assignments)
        run = MicrosoftService.active_run(db)
        if run is None:
            raise RuleViolationError(
                "Start Teams automation before distributing the deployment list"
            )
        target_ids = set(run.target_employee_ids or [])
        outside_scope = [
            employee.name for employee in people.values() if str(employee.id) not in target_ids
        ]
        if outside_scope:
            raise RuleViolationError(
                "Deployment-list recipients are outside the active automation run: "
                + ", ".join(outside_scope)
            )

        delivered, skipped, failures = [], [], []
        for owner_name, items in assignments.items():
            employee = people[owner_name]
            existing = db.scalar(
                select(Message.id)
                .where(
                    Message.employee_id == employee.id,
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.created_at >= entry.updated_at,
                    Message.content.contains(entry.title, autoescape=True),
                )
                .limit(1)
            )
            if existing is not None:
                skipped.append(employee.name)
                continue
            try:
                content = MicrosoftService.follow_up_message_for(
                    employee.name, DeploymentListService.message_body(entry, items)
                )
                message = MicrosoftService.send_management_message(db, employee, content)
                db.add(
                    ConversationQuestion(
                        conversation_id=message.conversation_id,
                        message_id=message.id,
                        awaiting_field="work",
                        expected_answer_type="task_status_update",
                        asked_to_employee_id=employee.id,
                        status="awaiting_response",
                    )
                )
                db.commit()
                delivered.append(employee.name)
            except Exception as exc:
                db.rollback()
                failures.append({"employee": employee.name, "error": str(exc)})
        task_changes = 0
        if not failures:
            try:
                task_changes = DeploymentListService.sync_tasks(db, entry, assignments, people)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {
            "source_id": str(entry.id),
            "task_changes": task_changes,
            "delivered": delivered,
            "skipped": skipped,
            "failures": failures,
        }
