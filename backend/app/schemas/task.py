import uuid
from datetime import datetime

from app.db.enums import TaskStatus
from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TaskScope(BaseModel):
    discovery_mode: str = Field(default="restricted", pattern="^(restricted|automatic)$")
    form_policy: str = Field(default="approval", pattern="^(approval|synthetic_with_approval)$")
    request_login: bool = False
    request_budget_extension: bool = False
    urls: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    allow_bug_filing: bool = False
    focus: str = ""  # extra instruction, e.g. set for the sub-tasks of a parallel run
    # Generic tasks (a Prism's computer): the plan's steps and the only sites the browser may open.
    steps: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    goal: str = ""
    scope: TaskScope = Field(default_factory=TaskScope)
    agent_id: uuid.UUID
    target_app_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    schedule_cron: str | None = Field(default=None, max_length=100)
    operation_key: str | None = Field(default=None, min_length=8, max_length=200)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    goal: str | None = None
    scope: TaskScope | None = None
    agent_id: uuid.UUID | None = None
    target_app_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    schedule_cron: str | None = Field(default=None, max_length=100)


class TaskRead(ORMModel):
    id: uuid.UUID
    title: str
    goal: str
    scope: TaskScope
    agent_id: uuid.UUID
    target_app_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    status: TaskStatus
    schedule_cron: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
