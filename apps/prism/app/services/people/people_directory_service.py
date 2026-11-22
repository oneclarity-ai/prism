from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import quote

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.people.employee import Employee
from app.models.prisms.prism_v22 import PrismPerson
from app.models.teams.microsoft_connection import MicrosoftConnection
from app.schemas.people.people import (
    PeopleRead,
    PeopleSyncResult,
    PersonRead,
    PersonUpdate,
)
from app.services.errors import (
    ExternalServiceError,
    NotFoundError,
    RuleViolationError,
)
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.teams.microsoft_service import MicrosoftGraphClient, MicrosoftService

USER_FIELDS = "id,displayName,mail,userPrincipalName,jobTitle,department,accountEnabled"
MAX_PEOPLE = 200
MAX_TEAM = 300
TEAM_DEPTH = 4
CHAIN_LIMIT = 50
# Fields a person edits by hand. A later Microsoft sync never replaces these.
OVERRIDABLE = ("title", "department", "manager_id")


def _clean(value: Any) -> str | None:
    text = str(value).strip() if isinstance(value, str) else ""
    return text or None


class PeopleDirectoryService:
    """Who the user is, who they chat with, and how those people relate to each other."""

    # --- Sync from Microsoft ---------------------------------------------------------------

    @staticmethod
    def sync(db: Session) -> PeopleSyncResult:
        """Read the people in the user's Teams chats and their Microsoft managers.

        Reads only: it never messages anyone. Hand edits are kept.
        """

        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        my_id = connection.microsoft_user_id

        seen: dict[str, dict[str, Any]] = {}
        for chat in graph.list_chats():
            raw_last = chat.get("lastMessagePreview")
            raw_last = raw_last.get("createdDateTime") if isinstance(raw_last, dict) else None
            last = MicrosoftService._parse_graph_datetime(
                raw_last or chat.get("lastUpdatedDateTime")
            )
            members = chat.get("members") if isinstance(chat.get("members"), list) else []
            for member in members:
                if not isinstance(member, dict):
                    continue
                user_id = member.get("userId") or member.get("id")
                if not isinstance(user_id, str) or user_id == my_id:
                    continue
                entry = seen.setdefault(user_id, {"name": None, "email": None, "last": None})
                entry["name"] = entry["name"] or _clean(member.get("displayName"))
                entry["email"] = entry["email"] or _clean(member.get("email"))
                if last and (entry["last"] is None or last > entry["last"]):
                    entry["last"] = last

        now = datetime.now(timezone.utc)
        counts = {"people": 0, "team": 0, "managers_added": 0, "skipped": 0}

        # Me first, so the user is always known even with no chats.
        me_profile = PeopleDirectoryService._fetch(graph, "me")
        me_found = False
        if me_profile is not None:
            me_profile.setdefault("id", my_id)
            me = PeopleDirectoryService._upsert(db, my_id, me_profile, now=now)
            if me is not None:
                me_found = True
                PeopleDirectoryService._link_manager(db, graph, me, "me", now=now, counts=counts)
                PeopleDirectoryService._sync_team(db, graph, me, now=now, counts=counts)

        for user_id, entry in list(seen.items())[:MAX_PEOPLE]:
            profile = PeopleDirectoryService._fetch(graph, f"users/{quote(user_id, safe='')}")
            if profile is None:
                # Guests and deleted users cannot be looked up; use what the chat gave us.
                if not entry["email"] or not entry["name"]:
                    counts["skipped"] += 1
                    continue
                profile = {"id": user_id, "displayName": entry["name"], "mail": entry["email"]}
            profile.setdefault("displayName", entry["name"])
            profile.setdefault("mail", entry["email"])
            employee = PeopleDirectoryService._upsert(
                db, user_id, profile, now=now, in_chats=True, last_chat=entry["last"]
            )
            if employee is None:
                counts["skipped"] += 1
                continue
            counts["people"] += 1
            PeopleDirectoryService._link_manager(
                db,
                graph,
                employee,
                f"users/{quote(user_id, safe='')}",
                now=now,
                counts=counts,
            )
        db.commit()
        return PeopleSyncResult(me_found=me_found, **counts)

    @staticmethod
    def _fetch(graph: MicrosoftGraphClient, path: str) -> dict[str, Any] | None:
        """One user's profile, or None when Microsoft has none (guest, deleted, no manager)."""

        try:
            return graph.request("GET", f"/{path}?$select={USER_FIELDS}")
        except ExternalServiceError:
            return None

    @staticmethod
    def _fetch_all(graph: MicrosoftGraphClient, path: str) -> list[dict[str, Any]]:
        """Every page of a Graph collection of users; empty when Microsoft will not list it."""

        rows: list[dict[str, Any]] = []
        url: str = f"/{path}?$select={USER_FIELDS}&$top=100"
        while url:
            try:
                payload = graph.request("GET", url)
            except ExternalServiceError:
                return rows
            values = payload.get("value", [])
            rows.extend(item for item in values if isinstance(item, dict))
            next_link = payload.get("@odata.nextLink")
            url = next_link if isinstance(next_link, str) else ""
        return rows

    @staticmethod
    def _sync_team(
        db: Session,
        graph: MicrosoftGraphClient,
        me: Employee,
        *,
        now: datetime,
        counts: dict[str, int],
    ) -> None:
        """The user's whole reporting team from the org chart, whether or not they have chatted."""

        frontier: list[tuple[Employee, str]] = [(me, "me")]
        seen: set[str] = set()
        for _ in range(TEAM_DEPTH):
            next_frontier: list[tuple[Employee, str]] = []
            for parent, path in frontier:
                for raw in PeopleDirectoryService._fetch_all(
                    graph, f"{path}/directReports/microsoft.graph.user"
                ):
                    user_id = raw.get("id")
                    if (
                        not isinstance(user_id, str)
                        or user_id in seen
                        or raw.get("accountEnabled") is False
                    ):
                        continue
                    if len(seen) >= MAX_TEAM:
                        return
                    seen.add(user_id)
                    employee = PeopleDirectoryService._upsert(db, user_id, raw, now=now)
                    if employee is None or employee.id == parent.id:
                        counts["skipped"] += 1
                        continue
                    employee.in_team = True
                    counts["team"] += 1
                    overrides = employee.field_overrides or []
                    if "manager_id" not in overrides and not (
                        PeopleDirectoryService._ancestor_ids(db, parent.id) & {employee.id}
                    ):
                        employee.manager_id = parent.id
                    db.flush()
                    next_frontier.append((employee, f"users/{quote(user_id, safe='')}"))
            frontier = next_frontier
            if not frontier:
                return

    @staticmethod
    def _upsert(
        db: Session,
        user_id: str,
        profile: dict[str, Any],
        *,
        now: datetime,
        in_chats: bool = False,
        last_chat: datetime | None = None,
    ) -> Employee | None:
        email = _clean(profile.get("mail")) or _clean(profile.get("userPrincipalName"))
        name = _clean(profile.get("displayName")) or email
        if not email or not name:
            return None
        email = email.lower()
        employee = db.scalar(select(Employee).where(Employee.teams_user_id == user_id))
        if employee is None:
            employee = db.scalar(select(Employee).where(Employee.email == email))
        if employee is None:
            employee = Employee(
                name=name, email=email, role="Team member", teams_user_id=user_id, is_active=True
            )
            db.add(employee)
        elif employee.teams_user_id not in (None, user_id):
            return None
        overrides = set(employee.field_overrides or [])
        employee.name = name
        employee.teams_user_id = user_id
        if "title" not in overrides:
            employee.title = _clean(profile.get("jobTitle"))
        if "department" not in overrides:
            employee.department = _clean(profile.get("department"))
        employee.is_active = True
        employee.directory_synced_at = now
        if in_chats:
            employee.in_chats = True
            if last_chat and (employee.last_chat_at is None or last_chat > employee.last_chat_at):
                employee.last_chat_at = last_chat
        db.flush()
        return employee

    @staticmethod
    def _link_manager(
        db: Session,
        graph: MicrosoftGraphClient,
        employee: Employee,
        path: str,
        *,
        now: datetime,
        counts: dict[str, int],
        depth: int = 0,
    ) -> None:
        if "manager_id" in (employee.field_overrides or []):
            return
        raw = PeopleDirectoryService._fetch(graph, f"{path}/manager")
        if raw is None or not isinstance(raw.get("id"), str):
            return  # no manager visible; keep whatever we already had
        existing = db.scalar(select(Employee).where(Employee.teams_user_id == raw["id"]))
        manager = PeopleDirectoryService._upsert(db, raw["id"], raw, now=now)
        if manager is None or manager.id == employee.id:
            return
        if existing is None:
            counts["managers_added"] += 1
        if PeopleDirectoryService._ancestor_ids(db, manager.id) & {employee.id}:
            return  # would create a cycle
        employee.manager_id = manager.id
        db.flush()
        # Walk up the chain so the tree reaches the top, not just one level.
        if depth < 6 and manager.manager_id is None and manager.teams_user_id:
            PeopleDirectoryService._link_manager(
                db,
                graph,
                manager,
                f"users/{quote(manager.teams_user_id, safe='')}",
                now=now,
                counts=counts,
                depth=depth + 1,
            )

    @staticmethod
    def _ancestor_ids(db: Session, employee_id: uuid.UUID) -> set[uuid.UUID]:
        """The employee and everyone above them."""

        chain: set[uuid.UUID] = set()
        current: uuid.UUID | None = employee_id
        for _ in range(CHAIN_LIMIT):
            if current is None or current in chain:
                break
            chain.add(current)
            current = db.scalar(select(Employee.manager_id).where(Employee.id == current))
        return chain

    # --- Reading ---------------------------------------------------------------------------

    @staticmethod
    def me_employee(db: Session) -> Employee | None:
        connection = db.scalar(
            select(MicrosoftConnection).order_by(MicrosoftConnection.last_connected_at.desc())
        )
        if connection is None:
            return None
        return db.scalar(
            select(Employee).where(Employee.teams_user_id == connection.microsoft_user_id)
        )

    @staticmethod
    def _visible(db: Session) -> list[Employee]:
        """Me, people in chats, managed people, and everyone above them (so the tree connects)."""

        everyone = {
            item.id: item
            for item in db.scalars(select(Employee).where(Employee.is_active.is_(True)))
        }
        me = PeopleDirectoryService.me_employee(db)
        keep: set[uuid.UUID] = set()
        for item in everyone.values():
            if (
                item.in_chats
                or item.in_team
                or item.is_managed
                or (me is not None and item.id == me.id)
            ):
                current: uuid.UUID | None = item.id
                for _ in range(CHAIN_LIMIT):
                    if current is None or current in keep or current not in everyone:
                        break
                    keep.add(current)
                    current = everyone[current].manager_id
        return sorted((everyone[key] for key in keep), key=lambda item: item.name.lower())

    @staticmethod
    def overview(db: Session) -> PeopleRead:
        me = PeopleDirectoryService.me_employee(db)
        visible = PeopleDirectoryService._visible(db)
        parents = {item.id: item.manager_id for item in visible}
        names = {item.id: item.name for item in visible}
        reports = dict(
            db.execute(
                select(Employee.manager_id, func.count())
                .where(Employee.manager_id.is_not(None), Employee.is_active.is_(True))
                .group_by(Employee.manager_id)
            ).all()
        )

        def read(item: Employee) -> PersonRead:
            return PersonRead(
                id=item.id,
                name=item.name,
                email=item.email,
                title=item.title,
                department=item.department,
                responsibilities=item.responsibilities,
                notes=item.notes,
                manager_id=item.manager_id,
                manager_name=names.get(item.manager_id) if item.manager_id else None,
                is_me=me is not None and item.id == me.id,
                in_chats=item.in_chats,
                in_team=item.in_team,
                is_managed=item.is_managed,
                last_chat_at=item.last_chat_at,
                direct_report_count=int(reports.get(item.id, 0)),
                relationship=PeopleDirectoryService.relationship(
                    me.id if me else None, item.id, parents
                ),
                overrides=list(item.field_overrides or []),
            )

        rows = [read(item) for item in visible]
        synced = db.scalar(select(func.max(Employee.directory_synced_at)))
        return PeopleRead(
            me=next((row for row in rows if row.is_me), None),
            people=[row for row in rows if not row.is_me],
            synced_at=synced,
        )

    @staticmethod
    def relationship(
        me_id: uuid.UUID | None,
        person_id: uuid.UUID,
        parents: dict[uuid.UUID, uuid.UUID | None],
    ) -> str:
        """How a person relates to the user, in plain words."""

        if me_id is None:
            return "Colleague"
        if person_id == me_id:
            return "You"

        def above(start: uuid.UUID) -> list[uuid.UUID]:
            chain: list[uuid.UUID] = []
            current = parents.get(start)
            while current is not None and current not in chain and len(chain) < CHAIN_LIMIT:
                chain.append(current)
                current = parents.get(current)
            return chain

        mine, theirs = above(me_id), above(person_id)
        if parents.get(me_id) == person_id:
            return "Your manager"
        if parents.get(person_id) == me_id:
            return "Reports to you"
        if person_id in mine:
            return "Above you"
        if me_id in theirs:
            return "In your team"
        if parents.get(person_id) is not None and parents.get(person_id) == parents.get(me_id):
            return "Peer"
        return "Colleague"

    # --- Editing ---------------------------------------------------------------------------

    @staticmethod
    def update(db: Session, employee_id: uuid.UUID, data: PersonUpdate) -> Employee:
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("Person was not found")
        changes = data.model_dump(exclude_unset=True)
        overrides = set(employee.field_overrides or [])
        if "manager_id" in changes:
            manager_id = changes["manager_id"]
            if manager_id is not None:
                if manager_id == employee.id:
                    raise RuleViolationError("Someone cannot report to themselves")
                if db.get(Employee, manager_id) is None:
                    raise NotFoundError("The chosen manager was not found")
                if employee.id in PeopleDirectoryService._ancestor_ids(db, manager_id):
                    raise RuleViolationError(
                        "That would make the reporting line loop back on itself"
                    )
            employee.manager_id = manager_id
            overrides.add("manager_id")
        for field in ("title", "department"):
            if field in changes:
                setattr(employee, field, _clean(changes[field]))
                overrides.add(field)
        for field in ("responsibilities", "notes"):
            if field in changes:
                setattr(employee, field, _clean(changes[field]))
        employee.field_overrides = sorted(overrides)
        db.commit()
        db.refresh(employee)
        return employee

    @staticmethod
    def reset(db: Session, employee_id: uuid.UUID) -> Employee:
        """Hand-edited title, department and manager go back to what Microsoft says."""

        employee = db.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("Person was not found")
        employee.field_overrides = []
        db.commit()
        try:
            PeopleDirectoryService.sync(db)
        except (ExternalServiceError, RuleViolationError):
            pass  # not connected right now; the next sync restores the values
        db.refresh(employee)
        return employee

    # --- What a Prism may know -------------------------------------------------------------

    @staticmethod
    def prism_people(db: Session, prism_id: uuid.UUID) -> tuple[str, list[uuid.UUID]]:
        prism = PrismLifecycleService.get(db, prism_id)
        ids = list(
            db.scalars(select(PrismPerson.employee_id).where(PrismPerson.prism_id == prism_id))
        )
        return prism.people_scope, ids

    @staticmethod
    def set_prism_people(
        db: Session, prism_id: uuid.UUID, scope: str, employee_ids: Iterable[uuid.UUID]
    ) -> tuple[str, list[uuid.UUID]]:
        prism = PrismLifecycleService.get(db, prism_id, include_archived=False)
        wanted = set(employee_ids)
        if wanted:
            found = set(db.scalars(select(Employee.id).where(Employee.id.in_(wanted))))
            if found != wanted:
                raise NotFoundError("One of the chosen people was not found")
        prism.people_scope = scope
        db.execute(delete(PrismPerson).where(PrismPerson.prism_id == prism_id))
        if scope == "selected":
            db.add_all(PrismPerson(prism_id=prism_id, employee_id=item) for item in wanted)
        db.commit()
        return scope, sorted(wanted, key=str) if scope == "selected" else []

    # --- Context handed to a Prism's model -------------------------------------------------

    @staticmethod
    def manager_context(db: Session) -> dict[str, Any] | None:
        """Who the user is, so every Prism can address and understand them."""

        me = PeopleDirectoryService.me_employee(db)
        if me is None:
            return None
        manager = db.get(Employee, me.manager_id) if me.manager_id else None
        profile = {
            "name": me.name,
            "first_name": me.name.split()[0],
            "job_title": me.title,
            "department": me.department,
            "reports_to": manager.name if manager else None,
            "what_i_do": me.responsibilities,
            "how_i_like_to_work": me.notes,
        }
        return {key: value for key, value in profile.items() if value}

    @staticmethod
    def people_context(
        db: Session,
        prism_id: uuid.UUID | None,
        *,
        names: Iterable[str] | None = None,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        """The people this Prism may know, with role and reporting line.

        With names given, only those people (matched on any name part) are returned.
        """

        visible = PeopleDirectoryService._visible(db)
        me = PeopleDirectoryService.me_employee(db)
        if prism_id is not None:
            scope, allowed = PeopleDirectoryService.prism_people(db, prism_id)
            if scope == "selected":
                keep = set(allowed)
                visible = [item for item in visible if item.id in keep]
        parents = {item.id: item.manager_id for item in PeopleDirectoryService._visible(db)}
        by_id = {item.id: item for item in visible}
        if me is not None:
            by_id[me.id] = me  # the user's own name is always usable in a reporting line
        wanted = {part.lower() for name in (names or []) for part in name.split() if len(part) > 1}
        rows: list[dict[str, Any]] = []
        for item in visible:
            if me is not None and item.id == me.id:
                continue
            if names is not None and not wanted & {part.lower() for part in item.name.split()}:
                continue
            chain: list[str] = []
            current = item.manager_id
            while current in by_id and len(chain) < 4 and by_id[current].name not in chain:
                chain.append(by_id[current].name)
                current = by_id[current].manager_id
            row = {
                "name": item.name,
                "job_title": item.title,
                "department": item.department,
                "what_they_do": item.responsibilities,
                "notes": item.notes,
                "relationship_to_manager": PeopleDirectoryService.relationship(
                    me.id if me else None, item.id, parents
                ),
                "reports_to": chain[0] if chain else None,
                "escalation_chain": chain,
            }
            rows.append({key: value for key, value in row.items() if value})
            if len(rows) >= limit:
                break
        return rows
