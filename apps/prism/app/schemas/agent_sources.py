from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import Schema


class TeamsParticipantRead(Schema):
    external_id: str | None = None
    display_name: str
    aliases: list[str] = Field(default_factory=list)


class TeamsChatSourceRead(Schema):
    external_id: str
    label: str
    chat_type: str
    participants: list[str]
    participant_details: list[TeamsParticipantRead] = Field(default_factory=list)
    last_updated_at: datetime | None = None


class TeamsChatSourcePage(Schema):
    items: list[TeamsChatSourceRead]
    total: int = Field(ge=0)


class TeamsChatSelection(Schema):
    external_id: str = Field(min_length=1, max_length=512)


class TeamsSourceResolutionRequest(Schema):
    goal: str = Field(min_length=1, max_length=4000)
    constrained_external_id: str | None = Field(default=None, max_length=512)
    selected_external_id: str | None = Field(default=None, max_length=512)
    selected_external_ids: list[str] = Field(default_factory=list, max_length=12)


class TeamsSourceResolutionCandidate(Schema):
    source: TeamsChatSourceRead
    rationale: str
    score: int = Field(ge=0)


class TeamsSourceResolutionRead(Schema):
    status: str = Field(pattern=r"^(resolved|ambiguous|needs_choice)$")
    selected: TeamsChatSourceRead | None = None
    selected_sources: list[TeamsChatSourceRead] = Field(default_factory=list)
    candidates: list[TeamsSourceResolutionCandidate] = Field(default_factory=list)
    rationale: str
    selection_reason: str
    excluded_external_ids: list[str] = Field(default_factory=list)
    limits: dict[str, int]


class AgentEvidenceRead(Schema):
    id: uuid.UUID
    source_message_id: str
    source_external_id: str
    source_label: str
    sender_display_name: str
    sent_at: datetime
    excerpt: str
    quoted_excerpt: str | None
    reply_to_source_id: str | None


class TeamsEvidenceSyncRead(Schema):
    job_id: uuid.UUID
    source_label: str
    source_labels: list[str] = Field(default_factory=list)
    fetched: int = Field(ge=0)
    stored: int = Field(ge=0)
    skipped: int = Field(ge=0)
    source_errors: list[dict[str, str]] = Field(default_factory=list)
    evidence: list[AgentEvidenceRead]
