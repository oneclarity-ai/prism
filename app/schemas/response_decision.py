from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueDecision(DecisionModel):
    key: str = Field(min_length=1, max_length=80)
    blocker_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    operation: Literal["report_blocker", "set_owners", "eta", "delivered", "complete_task"]
    description: str = Field(min_length=1, max_length=2000)
    dependency_owner_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    evidence: str = Field(min_length=1, max_length=3000)
    deadline: Optional[datetime] = None
    missed_reason: Optional[str] = None


class OutgoingDecision(DecisionModel):
    recipient_id: uuid.UUID
    issue_key: Optional[str] = None
    kind: Literal[
        "acknowledgement", "clarification", "dependency_followup", "status_update", "conversation"
    ]
    text: str = Field(min_length=1, max_length=1500)
    awaiting_field: Optional[Literal["owner", "eta", "completion", "outcome", "issue", "work"]] = None


class CommitmentDecision(DecisionModel):
    """A literal, deadline-bearing promise that is not necessarily a blocker ETA."""

    task_id: Optional[uuid.UUID] = None
    description: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=3000)
    deadline: datetime


class ResponseDecision(DecisionModel):
    intent: Literal[
        "acknowledgement", "work_update", "blocker", "commitment", "task_completion",
        "correction", "question", "conversation", "unclear",
    ] = "unclear"
    should_respond: bool
    response_type: Literal[
        "acknowledgement", "clarification", "dependency_followup", "status_update",
        "escalation", "conversation", "no_response",
    ]
    reason: str = Field(max_length=1000)
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool
    missing_information: list[str] = Field(default_factory=list, max_length=8)
    today_summary: Optional[str] = None
    completed_summary: Optional[str] = None
    expected_outcome: Optional[str] = None
    explicitly_no_blockers: bool = False
    issues: list[IssueDecision] = Field(default_factory=list, max_length=8)
    commitments: list[CommitmentDecision] = Field(default_factory=list, max_length=8)
    messages: list[OutgoingDecision] = Field(default_factory=list, max_length=12)
    answered_question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
