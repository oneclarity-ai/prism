from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMResponse, Schema
from app.schemas.prisms.agent_v21 import ActionProposalRead, AgentActionPlanRead, ToolExecutionRead


class ReviewAttentionItem(Schema):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    kind: str = Field(default="direct", pattern=r"^(direct|inference|conflict)$")
    source_external_ids: list[str] = Field(default_factory=list, max_length=12)


class ReviewManagerQuestion(Schema):
    question: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class ReviewProposedReply(Schema):
    body: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1500)
    # Empty only for drafts based solely on the manager's instruction (no Teams messages exist);
    # ConversationReviewService requires citations for every grounded review.
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class ReviewProposedAction(Schema):
    destination_source_id: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    sequence: int = Field(ge=1, le=12)
    depends_on_source_ids: list[str] = Field(default_factory=list, max_length=12)


class InstructionDraftAction(Schema):
    destination_source_id: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1500)
    sequence: int = Field(ge=1, le=12)
    depends_on_source_ids: list[str] = Field(default_factory=list, max_length=12)


class InstructionDraftOutput(Schema):
    """Model output when the selected chats are empty and the manager's words are the only input."""

    summary: str = Field(min_length=1, max_length=3000)
    proposed_actions: list[InstructionDraftAction] = Field(min_length=1, max_length=12)
    action_plan_summary: str | None = Field(default=None, max_length=1500)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    applied_preference_ids: list[str] = Field(default_factory=list, max_length=30)


class ConversationReviewOutput(Schema):
    summary: str = Field(min_length=1, max_length=3000)
    summary_evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    attention_items: list[ReviewAttentionItem] = Field(default_factory=list, max_length=12)
    manager_questions: list[ReviewManagerQuestion] = Field(default_factory=list, max_length=12)
    requires_reply: bool
    proposed_reply: ReviewProposedReply | None = None
    action_plan_summary: str | None = Field(default=None, max_length=1500)
    proposed_actions: list[ReviewProposedAction] = Field(default_factory=list, max_length=12)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    applied_preference_ids: list[str] = Field(default_factory=list, max_length=30)


class AgentConversationReviewRead(ORMResponse):
    id: uuid.UUID
    job_id: uuid.UUID
    summary: str
    summary_evidence_ids: list[str]
    attention_items: list[ReviewAttentionItem]
    manager_questions: list[ReviewManagerQuestion]
    requires_reply: bool
    proposed_reply: ReviewProposedReply | None
    confidence: float
    limitations: list[str]
    applied_preferences: list[dict] = Field(default_factory=list)
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime
    proposal: ActionProposalRead | None = None
    execution: ToolExecutionRead | None = None
    action_plan: AgentActionPlanRead | None = None
