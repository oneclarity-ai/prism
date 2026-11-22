"""Explicit input contracts for Workspace setup forms; never an arbitrary engine proxy."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr

from app.schemas.common import Schema


class WorkspaceTask(Schema):
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(default="", max_length=30000)
    agent_id: uuid.UUID
    target_app_id: uuid.UUID | None = None


class WorkspacePosition(Schema):
    title: str = Field(min_length=1, max_length=200)
    department: str = Field(default="Leadership", min_length=1, max_length=100)
    level: Literal["ceo", "executive", "senior_manager", "manager", "member"] = "member"
    holder_type: Literal["vacant", "human", "agent"] = "vacant"
    holder_name: str = Field(default="", max_length=200)
    agent_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    description: str = Field(default="", max_length=30000)


class WorkspaceTarget(Schema):
    name: str = Field(min_length=1, max_length=200)
    base_url: AnyHttpUrl
    environment: Literal["local", "dev", "staging", "production"] = "staging"
    notes: str = Field(default="", max_length=30000)


class WorkspaceSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    value: SecretStr = Field(min_length=1, max_length=100000)
    scope: str = Field(default="general", min_length=1, max_length=200, pattern=r"\S")
