"""Skill instructions never carry executable code or grant tool access."""

import uuid

from pydantic import Field, field_validator

from app.schemas.common import ORMResponse, Schema


class SkillContent(Schema):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=2000)
    required_tools: list[str] = Field(default_factory=list, max_length=20)
    required_connections: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("name", "description", "instructions")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter text rather than spaces")
        return value.strip()

    @field_validator("required_tools", "required_connections")
    @classmethod
    def bounded_names(cls, values: list[str]) -> list[str]:
        names = list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
        if any(len(name) > 80 for name in names):
            raise ValueError("Requirement names must be at most 80 characters")
        return names


class SkillRead(SkillContent, ORMResponse):
    id: uuid.UUID
    owner_prism_id: uuid.UUID | None = None
    revision: int
    archived: bool


class SkillUpdate(SkillContent):
    expected_revision: int = Field(ge=1)
    archived: bool = False


class SkillAssign(Schema):
    expected_skill_revision: int = Field(ge=1)
    expected_assignment_revision: int = Field(default=0, ge=0)
    enabled: bool


class PrismSkillEdit(SkillUpdate):
    expected_assignment_revision: int = Field(ge=1)


class SkillInterviewAnswer(Schema):
    expected_revision: int = Field(ge=1)
    key: str = Field(max_length=30)
    answer: str = Field(min_length=1, max_length=2000)

    @field_validator("answer")
    @classmethod
    def nonblank(cls, value: str) -> str:
        return SkillContent.nonblank(value)


class SkillApproval(Schema):
    expected_revision: int = Field(ge=1)
    skills: list[SkillContent] = Field(default_factory=list, max_length=4)
