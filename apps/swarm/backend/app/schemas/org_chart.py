import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

Level = Literal["ceo", "executive", "senior_manager", "manager", "member"]
HolderType = Literal["vacant", "human", "agent"]


class PositionBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    level: Level = "member"
    department: str = Field(default="Leadership", min_length=1, max_length=100)
    holder_type: HolderType = "vacant"
    holder_name: str = Field(default="", max_length=200)
    agent_id: uuid.UUID | None = None
    planned_agent_key: str | None = Field(default=None, max_length=64)
    description: str = ""
    sort_order: int = 0


class PositionCreate(PositionBase):
    parent_id: uuid.UUID | None = None


class PositionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    level: Level | None = None
    department: str | None = Field(default=None, min_length=1, max_length=100)
    holder_type: HolderType | None = None
    holder_name: str | None = Field(default=None, max_length=200)
    agent_id: uuid.UUID | None = None
    planned_agent_key: str | None = None
    description: str | None = None
    sort_order: int | None = None
    parent_id: uuid.UUID | None = None


class PositionRead(ORMModel, PositionBase):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AgentRoleRead(BaseModel):
    key: str
    name: str
    role: str
    department: str
    description: str
    status: Literal["available", "planned"]
    runtime: str
