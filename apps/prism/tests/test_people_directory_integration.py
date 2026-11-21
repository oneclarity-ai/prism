from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.people.employee import Employee
from app.models.prisms.agent_v21 import AgentThread
from app.models.prisms.prism_v22 import Prism
from app.schemas.people.people import PersonUpdate
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.errors import RuleViolationError
from app.services.people import people_directory_service as module
from app.services.people.people_directory_service import PeopleDirectoryService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService


@pytest.fixture
def org(monkeypatch):
    """A fake Microsoft tenant: me -> boss -> ceo, and two chat people under me."""

    tag = uuid.uuid4().hex[:8]
    ids = {
        key: f"{key}-{tag}"
        for key in ("me", "asha", "ravi", "boss", "ceo", "ghost", "dev", "intern")
    }
    profiles = {
        "me": ("Yash Mandi", "Engineering Manager", "Engineering", "boss"),
        "asha": ("Asha Rao", "Backend Engineer", "Engineering", "me"),
        "ravi": ("Ravi Iyer", "Designer", "Design", "boss"),
        "boss": ("Bela Boss", "VP Engineering", "Engineering", "ceo"),
        "ceo": ("Carl Ceo", "CEO", "Executive", None),
        # Never chatted with the user: found only through the org chart.
        "dev": ("Dev Das", "Frontend Engineer", "Engineering", "me"),
        "intern": ("Ina Intern", "Intern", "Engineering", "dev"),
    }
    reports = {"me": ["asha", "dev"], "dev": ["intern"]}

    class FakeGraph:
        def __init__(self, _db, _connection) -> None:
            pass

        def list_chats(self):
            def member(key):
                return {"userId": ids[key], "displayName": profiles[key][0]}

            return [
                {
                    "id": f"c1-{tag}",
                    "chatType": "oneOnOne",
                    "lastUpdatedDateTime": "2026-10-30T10:00:00Z",
                    "members": [member("me"), member("asha")],
                },
                {
                    "id": f"c2-{tag}",
                    "chatType": "group",
                    "lastUpdatedDateTime": "2026-10-31T09:00:00Z",
                    "members": [member("me"), member("ravi"), member("asha")],
                },
                {
                    "id": f"c3-{tag}",
                    "chatType": "group",
                    "members": [
                        {
                            "userId": ids["ghost"],
                            "displayName": "Guest Gus",
                            "email": f"gus-{tag}@x.io",
                        }
                    ],
                },
            ]

        def request(self, method, path):
            path = path.split("?")[0]
            if path.endswith("/directReports/microsoft.graph.user"):
                owner = path.removesuffix("/directReports/microsoft.graph.user")
                key = (
                    "me"
                    if owner == "/me"
                    else next(k for k, v in ids.items() if owner == f"/users/{v}")
                )
                return {"value": [self._user(k) for k in reports.get(key, [])]}
            if path == "/me":
                return self._user("me")
            if path == "/me/manager":
                return self._user(profiles["me"][3])
            for key, value in ids.items():
                if path == f"/users/{value}":
                    if key == "ghost":
                        from app.services.errors import ExternalServiceError

                        raise ExternalServiceError("not found")
                    return self._user(key)
                if path == f"/users/{value}/manager":
                    boss = profiles[key][3] if key in profiles else None
                    if boss is None:
                        from app.services.errors import ExternalServiceError

                        raise ExternalServiceError("no manager")
                    return self._user(boss)
            raise AssertionError(f"unexpected Graph call {path}")

        def _user(self, key):
            name, title, department, _ = profiles[key]
            return {
                "id": ids[key],
                "displayName": name,
                "mail": f"{key}-{tag}@example.com",
                "jobTitle": title,
                "department": department,
            }

    monkeypatch.setattr(module, "MicrosoftGraphClient", FakeGraph)
    monkeypatch.setattr(
        module.MicrosoftService,
        "get_connection",
        staticmethod(lambda _db: SimpleNamespace(microsoft_user_id=ids["me"])),
    )
    monkeypatch.setattr(
        PeopleDirectoryService,
        "me_employee",
        staticmethod(
            lambda db: db.scalar(select(Employee).where(Employee.teams_user_id == ids["me"]))
        ),
    )
    yield SimpleNamespace(ids=ids, tag=tag)
    with SessionLocal() as db:
        db.execute(
            delete(Employee).where(
                Employee.teams_user_id.in_(list(ids.values())) | Employee.email.like(f"%-{tag}@%")
            )
        )
        db.commit()


def _by_name(overview):
    return {row.name: row for row in [overview.me, *overview.people] if row}


def test_sync_builds_me_the_chat_people_and_the_reporting_lines(org) -> None:
    with SessionLocal() as db:
        result = PeopleDirectoryService.sync(db)
        assert result.me_found and result.people == 3 and result.team == 3 and result.skipped == 0
        # Guest Gus cannot be looked up in the directory: kept from the chat itself.
        assert result.managers_added >= 2

        overview = PeopleDirectoryService.overview(db)
        people = _by_name(overview)
        assert overview.me.name == "Yash Mandi" and overview.me.is_me
        assert overview.me.title == "Engineering Manager"
        assert overview.me.manager_name == "Bela Boss"
        assert people["Asha Rao"].relationship == "Reports to you"
        assert people["Asha Rao"].in_chats and people["Asha Rao"].manager_name == "Yash Mandi"
        assert people["Bela Boss"].relationship == "Your manager"
        assert not people["Bela Boss"].in_chats  # shown only so the tree connects
        assert people["Carl Ceo"].relationship == "Above you"
        assert people["Ravi Iyer"].relationship == "Peer"
        assert overview.me.direct_report_count == 2
        # Dev and Ina never chatted with the user, but are in the reporting team.
        assert people["Dev Das"].in_team and not people["Dev Das"].in_chats
        assert people["Dev Das"].relationship == "Reports to you"
        assert people["Ina Intern"].relationship == "In your team"
        assert people["Ina Intern"].manager_name == "Dev Das"


def test_hand_edits_survive_a_sync_until_reset(org) -> None:
    with SessionLocal() as db:
        PeopleDirectoryService.sync(db)
        asha = db.scalar(select(Employee).where(Employee.teams_user_id == org.ids["asha"]))
        PeopleDirectoryService.update(
            db,
            asha.id,
            PersonUpdate(title="Tech Lead", responsibilities="Owns the billing service"),
        )
        PeopleDirectoryService.sync(db)
        db.refresh(asha)
        assert asha.title == "Tech Lead" and "title" in asha.field_overrides
        assert asha.responsibilities == "Owns the billing service"
        assert asha.department == "Engineering"  # not edited, so still follows Microsoft

        PeopleDirectoryService.reset(db, asha.id)
        db.refresh(asha)
        assert asha.title == "Backend Engineer" and asha.field_overrides == []
        assert asha.responsibilities == "Owns the billing service"  # your notes are kept


def test_reporting_lines_cannot_loop(org) -> None:
    with SessionLocal() as db:
        PeopleDirectoryService.sync(db)
        me = PeopleDirectoryService.me_employee(db)
        asha = db.scalar(select(Employee).where(Employee.teams_user_id == org.ids["asha"]))
        with pytest.raises(RuleViolationError):
            PeopleDirectoryService.update(db, me.id, PersonUpdate(manager_id=asha.id))
        with pytest.raises(RuleViolationError):
            PeopleDirectoryService.update(db, asha.id, PersonUpdate(manager_id=asha.id))


def test_prisms_know_the_manager_and_only_the_people_they_may(org, monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    get_settings.cache_clear()
    created: list[uuid.UUID] = []
    try:
        with SessionLocal() as db:
            PeopleDirectoryService.sync(db)
            me = PeopleDirectoryService.me_employee(db)
            PeopleDirectoryService.update(
                db, me.id, PersonUpdate(responsibilities="Runs engineering delivery")
            )
            context = PeopleDirectoryService.manager_context(db)
            assert context["first_name"] == "Yash"
            assert context["reports_to"] == "Bela Boss"
            assert context["what_i_do"] == "Runs engineering delivery"

            everyone = {p["name"] for p in PeopleDirectoryService.people_context(db, None)}
            assert {"Asha Rao", "Ravi Iyer", "Bela Boss"} <= everyone

            asha_row = next(
                p for p in PeopleDirectoryService.people_context(db, None, names=["Asha"])
            )
            assert asha_row["reports_to"] == "Yash Mandi"
            assert asha_row["escalation_chain"][:2] == ["Yash Mandi", "Bela Boss"]

            prism = PrismLifecycleService.create(
                db, PrismCreate(name=f"Eng {org.tag}", description="Engineering Prism.")
            )
            created.append(prism.id)
            asha = db.scalar(select(Employee).where(Employee.teams_user_id == org.ids["asha"]))
            PeopleDirectoryService.set_prism_people(db, prism.id, "selected", [asha.id])
            visible = {p["name"] for p in PeopleDirectoryService.people_context(db, prism.id)}
            assert visible == {"Asha Rao"}
            scoped = PeopleDirectoryService.people_context(db, prism.id)[0]
            # Bela Boss is outside this Prism's people, so the chain stops before them.
            assert scoped["escalation_chain"] == ["Yash Mandi"]

            PeopleDirectoryService.set_prism_people(db, prism.id, "all", [])
            assert "Ravi Iyer" in {
                p["name"] for p in PeopleDirectoryService.people_context(db, prism.id)
            }
    finally:
        get_settings.cache_clear()
        with SessionLocal() as db:
            db.execute(delete(AgentThread).where(AgentThread.prism_id.in_(created)))
            db.execute(delete(Prism).where(Prism.id.in_(created)))
            db.commit()


def test_people_api_roundtrip(org, monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V22_ENABLED", "true")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        assert client.post("/api/v1/people/sync").json()["me_found"] is True
        body = client.get("/api/v1/people").json()
        assert body["me"]["name"] == "Yash Mandi"
        asha = next(p for p in body["people"] if p["name"] == "Asha Rao")
        patched = client.patch(
            f"/api/v1/people/{asha['id']}", json={"department": "Platform"}
        ).json()
        updated = next(p for p in patched["people"] if p["id"] == asha["id"])
        assert updated["department"] == "Platform" and updated["overrides"] == ["department"]
        reset = client.post(f"/api/v1/people/{asha['id']}/reset").json()
        assert next(p for p in reset["people"] if p["id"] == asha["id"])["overrides"] == []
    finally:
        get_settings.cache_clear()
