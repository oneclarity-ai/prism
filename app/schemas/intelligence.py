from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import ORMResponse, Schema


class StateItem(Schema):
    id: uuid.UUID
    kind: str
    summary: str
    status: Optional[str] = None
    employee_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    blocker_id: Optional[uuid.UUID] = None
    commitment_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    occurred_at: Optional[datetime] = None
    evidence: list[str] = Field(default_factory=list)


class EmployeeManagementState(Schema):
    employee_id: uuid.UUID
    employee_name: str
    generated_at: datetime
    active_work: list[StateItem] = Field(default_factory=list)
    current_blockers: list[StateItem] = Field(default_factory=list)
    dependencies_on_others: list[StateItem] = Field(default_factory=list)
    others_depending_on_employee: list[StateItem] = Field(default_factory=list)
    open_commitments: list[StateItem] = Field(default_factory=list)
    upcoming_deadlines: list[StateItem] = Field(default_factory=list)
    missed_commitments: list[StateItem] = Field(default_factory=list)
    awaiting_answers: list[StateItem] = Field(default_factory=list)
    recently_completed: list[StateItem] = Field(default_factory=list)
    recent_changes: list[StateItem] = Field(default_factory=list)
    open_followups: list[StateItem] = Field(default_factory=list)
    management_risks: list[StateItem] = Field(default_factory=list)


class DependencyEdgeRead(Schema):
    id: uuid.UUID
    source_entity_type: str
    source_entity_id: uuid.UUID
    target_entity_type: str
    target_entity_id: uuid.UUID
    relation_type: str = "depends_on"
    status: str
    blocker_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    confidence: float
    reopened_from_id: Optional[uuid.UUID] = None
    evidence: list[str] = Field(default_factory=list)


class DependencyEdgeCreate(Schema):
    source_entity_type: Literal["employee", "task", "project"]
    source_entity_id: uuid.UUID
    target_entity_type: Literal["employee", "task", "project"]
    target_entity_id: uuid.UUID
    blocker_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    source_message_id: Optional[uuid.UUID] = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class DependencyGraphRead(Schema):
    edges: list[DependencyEdgeRead]
    cycles: list[list[str]] = Field(default_factory=list)


class RiskRead(ORMResponse):
    id: uuid.UUID
    risk_type: str
    severity: str
    status: str
    source_entity_type: str
    source_entity_id: uuid.UUID
    summary: str
    reason: str
    recommended_action: str
    affected_entities: list
    signals: list
    evidence: list
    deadline_at_risk: Optional[datetime]
    confidence: float
    first_detected_at: datetime
    last_evaluated_at: datetime
    resolved_at: Optional[datetime]


class DecisionRead(ORMResponse):
    id: uuid.UUID
    trigger_type: str
    trigger_id: Optional[uuid.UUID]
    action: str
    status: str
    target_employee_ids: list
    related_issue_id: Optional[uuid.UUID]
    reason: str
    confidence: float
    evidence: list
    context: dict
    model: Optional[str]
    latency_ms: Optional[int]
    outcome: Optional[dict]
    decided_at: datetime
    executed_at: Optional[datetime]


class AttentionItem(Schema):
    risk: RiskRead
    people: list[str] = Field(default_factory=list)
    impact: str
    agent_actions: list[str] = Field(default_factory=list)
    current_expectation: str
    why_visible: str
    manager_options: list[str] = Field(default_factory=list)


class DailyBrief(Schema):
    date: date
    completed: list[str] = Field(default_factory=list)
    in_progress: list[str] = Field(default_factory=list)
    new_blockers: list[str] = Field(default_factory=list)
    resolved_blockers: list[str] = Field(default_factory=list)
    missed_commitments: list[str] = Field(default_factory=list)
    changed_etas: list[str] = Field(default_factory=list)
    dependencies_at_risk: list[str] = Field(default_factory=list)
    people_waiting: list[str] = Field(default_factory=list)
    needs_attention: list[str] = Field(default_factory=list)
    important_changes: list[str] = Field(default_factory=list)
    no_action_required: list[str] = Field(default_factory=list)


class ChangeRead(Schema):
    event_id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: Optional[uuid.UUID]
    employee_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    task_id: Optional[uuid.UUID]
    occurred_at: datetime
    summary: str
    previous: Optional[dict] = None
    current: Optional[dict] = None
    evidence: list[str] = Field(default_factory=list)


class ManagementQueryRequest(Schema):
    question: str = Field(min_length=2, max_length=1000)


class ManagementQueryAnswer(Schema):
    answer: str
    answer_type: str
    items: list[dict] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    uncertainty: Optional[str] = None


class ManagerFeedbackCreate(Schema):
    instruction_type: Literal[
        "one_time", "project_preference", "person_preference",
        "general_preference", "state_correction"
    ]
    scope: Literal["one_time", "project", "person", "general"]
    instruction: str = Field(min_length=3, max_length=4000)
    employee_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    source_message_id: Optional[uuid.UUID] = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_scope_target(self):
        if self.scope == "person" and self.employee_id is None:
            raise ValueError("Person-scoped feedback requires employee_id")
        if self.scope == "project" and self.project_id is None:
            raise ValueError("Project-scoped feedback requires project_id")
        return self


class ManagerFeedbackRead(ORMResponse):
    id: uuid.UUID
    instruction_type: str
    scope: str
    instruction: str
    employee_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    source_message_id: Optional[uuid.UUID]
    is_active: bool
    confidence: float
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class IntelligenceCycleResult(Schema):
    risks_evaluated: int = 0
    active_risks: int = 0
    decisions_created: int = 0
    no_action: int = 0


class ProactiveDecisionProposal(Schema):
    action: Literal[
        "NO_ACTION", "ACKNOWLEDGE", "ASK_CLARIFICATION", "FOLLOW_UP",
        "UPDATE_DEPENDENT", "CREATE_COMMITMENT", "UPDATE_COMMITMENT",
        "REQUEST_MANAGER_APPROVAL",
    ]
    target_employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    related_issue_id: Optional[uuid.UUID] = None
    reason: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)
