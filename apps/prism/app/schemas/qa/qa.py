from __future__ import annotations

import uuid

from pydantic import Field, SecretStr

from app.schemas.common import Schema


class QaStatusRead(Schema):
    available: bool
    reason: str | None = None
    computers: bool = False


class QaPlanCreate(Schema):
    thread_id: uuid.UUID
    content: str = Field(min_length=1, max_length=4000)


class QaPlanResult(Schema):
    handled: bool
    qa_run_id: uuid.UUID | None = None


class QaStart(Schema):
    pages: list[str] | None = Field(default=None, max_length=12)
    features: list[str] | None = Field(default=None, max_length=12)
    acceptance_criteria: list[str] | None = Field(default=None, max_length=12)
    max_turns: int | None = Field(default=None, ge=5, le=300)
    budget_usd: float | None = Field(default=None, gt=0, le=50)
    allow_bug_filing: bool | None = None
    # Tasks on a Prism's own computer
    steps: list[str] | None = Field(default=None, max_length=8)
    sites: list[str] | None = Field(default=None, max_length=8)
    any_public_site: bool | None = None


class QaLogin(Schema):
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=1, max_length=500)
    remember: bool = True


class QaDecision(Schema):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str = Field(default="", max_length=500)
    answer: str | None = Field(default=None, max_length=1000)  # for a question
    login: QaLogin | None = None  # for a sign-in card; never stored by Prism, never logged
