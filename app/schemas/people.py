from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import ORMResponse, Schema


class PersonRead(ORMResponse):
    id: uuid.UUID
    name: str
    email: str
    title: Optional[str]
    department: Optional[str]
    responsibilities: Optional[str]
    notes: Optional[str]
    manager_id: Optional[uuid.UUID]
    manager_name: Optional[str]
    is_me: bool
    in_chats: bool
    in_team: bool
    is_managed: bool
    last_chat_at: Optional[datetime]
    direct_report_count: int
    # How this person relates to the signed-in user, in plain words.
    relationship: str
    # Fields the user changed by hand; a sync never replaces these.
    overrides: list[str]


class PeopleRead(ORMResponse):
    me: Optional[PersonRead]
    people: list[PersonRead]
    synced_at: Optional[datetime]


class PersonUpdate(Schema):
    title: Optional[str] = Field(default=None, max_length=255)
    department: Optional[str] = Field(default=None, max_length=255)
    responsibilities: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    manager_id: Optional[uuid.UUID] = None


class PeopleSyncResult(Schema):
    people: int
    team: int
    managers_added: int
    skipped: int
    me_found: bool


class PrismPeopleRead(Schema):
    scope: Literal["all", "selected"]
    employee_ids: list[uuid.UUID]


class PrismPeopleUpdate(Schema):
    scope: Literal["all", "selected"]
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
