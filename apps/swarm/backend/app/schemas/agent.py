import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.enums import AgentStatus, ToolGrant
from app.schemas.common import ORMModel

KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,63}$"


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=64)
    description: str = ""
    instructions: str = ""
    runtime: str = "openai_agents"
    model: str = ""
    tool_grants: dict[str, ToolGrant] = Field(default_factory=dict)
    max_turns: int = Field(default=80, ge=1, le=500)
    run_budget_usd: Decimal = Field(default=Decimal("3.00"), ge=0)
    monthly_budget_usd: Decimal = Field(default=Decimal("100.00"), ge=0)
    reports_to_id: uuid.UUID | None = None


class AgentCreate(AgentBase):
    key: str = Field(pattern=KEY_PATTERN)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    instructions: str | None = None
    runtime: str | None = None
    model: str | None = None
    tool_grants: dict[str, ToolGrant] | None = None
    max_turns: int | None = Field(default=None, ge=1, le=500)
    run_budget_usd: Decimal | None = Field(default=None, ge=0)
    monthly_budget_usd: Decimal | None = Field(default=None, ge=0)
    reports_to_id: uuid.UUID | None = None


class JobDescriptionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=64)
    department: str = ""
    notes: str = Field(default="", max_length=4000, description="Anything the user already wrote about the agent")


class JobDescription(BaseModel):
    description: str
    cost_usd: float


class AgentRead(ORMModel, AgentBase):
    id: uuid.UUID
    key: str
    status: AgentStatus
    created_at: datetime
    updated_at: datetime
