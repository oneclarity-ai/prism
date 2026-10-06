from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models.enums import (
    ActivityEventType,
    ManagementProcedureStatus,
    MemoryFactStatus,
    MemoryPredicate,
    VisibilityScope,
)
from app.schemas.common import ORMResponse, Schema


class MemoryFactCreate(Schema):
    subject_type: str = Field(min_length=1, max_length=64)
    subject_id: Optional[uuid.UUID] = None
    subject_text: Optional[str] = None
    predicate: MemoryPredicate
    object_type: Optional[str] = None
    object_id: Optional[uuid.UUID] = None
    object_text: Optional[str] = None
    observed_at: datetime
    valid_from: Optional[datetime] = None
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    importance: int = Field(default=50, ge=0, le=100)
    visibility_scope: VisibilityScope = VisibilityScope.MANAGER_ONLY
    source_type: Optional[str] = None
    source_id: Optional[uuid.UUID] = None


class MemoryFactRead(ORMResponse):
    id: uuid.UUID
    subject_type: str
    subject_id: Optional[uuid.UUID]
    subject_text: Optional[str]
    predicate: MemoryPredicate
    object_type: Optional[str]
    object_id: Optional[uuid.UUID]
    object_text: Optional[str]
    observed_at: datetime
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    status: MemoryFactStatus
    confidence: Optional[int]
    importance: int
    supersedes_fact_id: Optional[uuid.UUID]
    visibility_scope: VisibilityScope
    created_at: datetime
    updated_at: datetime


class MemorySearchRead(Schema):
    facts: list[MemoryFactRead]
    episodes: list[dict]
    relations: list[dict]


class ActivityEventRead(ORMResponse):
    id: uuid.UUID
    event_type: ActivityEventType
    entity_type: str
    entity_id: Optional[uuid.UUID]
    source_type: str
    source_id: Optional[uuid.UUID]
    subject_employee_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    task_id: Optional[uuid.UUID]
    occurred_at: datetime
    recorded_at: datetime
    metadata_json: Optional[dict]


class ManagementProcedureRead(ORMResponse):
    id: uuid.UUID
    name: str
    description: str
    trigger_conditions: dict
    suggested_actions: dict
    status: ManagementProcedureStatus
    supporting_episode_count: int
    success_count: int
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]


class ProcedureDecision(Schema):
    approved_by: uuid.UUID


class CompiledMemoryContext(Schema):
    employee_id: uuid.UUID
    current_work: list[str] = []
    current_blockers: list[str] = []
    open_commitments: list[str] = []
    relevant_facts: list[str] = []
    relevant_episodes: list[str] = []
    relevant_relations: list[str] = []
    raw_evidence: list[str] = []
    uncertainties: list[str] = []

    def as_prompt(self) -> str:
        sections = [
            ("CURRENT WORK", self.current_work),
            ("CURRENT BLOCKERS", self.current_blockers),
            ("OPEN COMMITMENTS", self.open_commitments),
            ("RELEVANT MEMORY", self.relevant_facts),
            ("RELEVANT EPISODES", self.relevant_episodes),
            ("RELEVANT RELATIONSHIPS", self.relevant_relations),
            ("EVIDENCE", self.raw_evidence),
            ("UNCERTAINTIES", self.uncertainties),
        ]
        return "\n\n".join(
            "{}\n{}".format(title, "\n".join("- " + value for value in values))
            for title, values in sections
            if values
        )
