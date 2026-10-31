from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.agent_v21 import (
    ActionProposal,
    AgentFeedbackEvent,
    AgentJob,
    AgentPreference,
    AgentThread,
    AgentThreadMessage,
    ToolExecution,
)
from app.models.enums import ActionProposalState, AgentJobState
from app.schemas.agent_review import AgentConversationReviewRead
from app.schemas.agent_sources import (
    AgentEvidenceRead,
    TeamsChatSelection,
    TeamsChatSourcePage,
    TeamsEvidenceSyncRead,
    TeamsSourceResolutionRead,
    TeamsSourceResolutionRequest,
)
from app.schemas.agent_v21 import (
    ActionProposalCreate,
    ActionProposalRead,
    ActionProposalRevise,
    AgentActionPlanRead,
    AgentFeedbackCreate,
    AgentFoundationRead,
    AgentJobCreate,
    AgentJobRead,
    AgentJobTransition,
    AgentPreferenceCreate,
    AgentPreferenceRead,
    AgentPreferenceUpdate,
    AgentStepCreate,
    AgentStepRead,
    AgentStepTransition,
    AgentThreadCreate,
    AgentThreadMessageCreate,
    AgentThreadMessageRead,
    AgentThreadRead,
    ApprovalDecisionCreate,
    ApprovalDecisionRead,
    BulkApprovalCreate,
    ToolExecutionRead,
)
from app.services.agent_preference_service import AgentPreferenceService
from app.services.agent_recovery_service import AgentRecoveryService
from app.services.agent_state_service import AgentStateService
from app.services.approved_teams_execution_service import ApprovedTeamsExecutionService
from app.services.conversation_review_service import ConversationReviewService
from app.services.coordinated_action_service import CoordinatedActionService
from app.services.errors import RuleViolationError
from app.services.source_resolution_service import SourceResolutionService
from app.services.teams_read_service import TeamsReadService

router = APIRouter(prefix="/api/v2/agent", tags=["Prism v2.1 agent"])


THREAD_DESTINATION_PATTERN = re.compile(
    r"\b(?:in|to)\s+(?:this|the)\s+(?:group|chat)\b", re.IGNORECASE
)
EXPLICIT_CROSS_SOURCE_READ_PATTERN = re.compile(
    r"\b(?:read|check|review|use|based\s+on)\b[^.?!]{0,180}\b(?:chats|conversations|sources)\b",
    re.IGNORECASE,
)


def require_v21() -> None:
    if not get_settings().prism_v21_enabled:
        raise HTTPException(status_code=404, detail="Prism v2.1 is not enabled")


@router.get("/foundation", response_model=AgentFoundationRead, dependencies=[Depends(require_v21)])
def foundation(db: Session = Depends(get_db)) -> AgentFoundationRead:
    return AgentFoundationRead(
        enabled=True,
        threads=int(
            db.scalar(select(func.count(AgentThread.id)).where(AgentThread.is_canonical.is_(True)))
            or 0
        ),
        jobs=int(db.scalar(select(func.count(AgentJob.id))) or 0),
        pending_approvals=int(
            db.scalar(
                select(func.count(ActionProposal.id)).where(
                    ActionProposal.state == ActionProposalState.PENDING
                )
            )
            or 0
        ),
        executions=int(db.scalar(select(func.count(ToolExecution.id))) or 0),
        job_states=[state.value for state in AgentJobState],
        proposal_states=[state.value for state in ActionProposalState],
    )


@router.post(
    "/foundation/demo",
    response_model=AgentJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_foundation_demo(db: Session = Depends(get_db)) -> AgentJob:
    thread = AgentStateService.canonical_thread(db)
    job = AgentStateService.create_job(
        db, thread_id=thread.id, goal="Verify durable queued agent work"
    )
    AgentStateService.append_step(
        db, job_id=job.id, kind="foundation", label="Waiting for a future agent worker"
    )
    return _job(db, job.id)


@router.get("/threads", response_model=list[AgentThreadRead], dependencies=[Depends(require_v21)])
def list_threads(db: Session = Depends(get_db)) -> list[AgentThread]:
    return [AgentStateService.canonical_thread(db)]


@router.get("/conversation", response_model=AgentThreadRead, dependencies=[Depends(require_v21)])
def canonical_conversation(db: Session = Depends(get_db)) -> AgentThread:
    return AgentStateService.canonical_thread(db)


@router.get(
    "/threads/{thread_id}/resolve",
    response_model=AgentThreadRead,
    dependencies=[Depends(require_v21)],
)
def resolve_legacy_thread(thread_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentThread:
    return AgentStateService.resolve_thread(db, thread_id)


@router.get(
    "/preferences", response_model=list[AgentPreferenceRead], dependencies=[Depends(require_v21)]
)
def list_preferences(db: Session = Depends(get_db)) -> list[AgentPreference]:
    return AgentPreferenceService.list(db)


@router.post(
    "/preferences",
    response_model=AgentPreferenceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_preference(
    payload: AgentPreferenceCreate, db: Session = Depends(get_db)
) -> AgentPreference:
    return AgentPreferenceService.create(db, payload)


@router.put(
    "/preferences/{preference_id}",
    response_model=AgentPreferenceRead,
    dependencies=[Depends(require_v21)],
)
def update_preference(
    preference_id: uuid.UUID,
    payload: AgentPreferenceUpdate,
    db: Session = Depends(get_db),
) -> AgentPreference:
    return AgentPreferenceService.update(db, preference_id, payload)


@router.post(
    "/threads",
    response_model=AgentThreadRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_thread(payload: AgentThreadCreate, db: Session = Depends(get_db)) -> AgentThread:
    thread = AgentStateService.canonical_thread(db)
    if payload.source:
        thread.source_kind = payload.source.kind
        thread.source_external_id = payload.source.external_id
        thread.source_label = payload.source.label
        thread.source_metadata = payload.source.metadata
        db.commit()
        db.refresh(thread)
    return thread


@router.get(
    "/threads/{thread_id}/messages",
    response_model=list[AgentThreadMessageRead],
    dependencies=[Depends(require_v21)],
)
def list_thread_messages(
    thread_id: uuid.UUID,
    q: str | None = Query(default=None, max_length=200),
    before: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AgentThreadMessage]:
    thread = AgentStateService.resolve_thread(db, thread_id)
    query = select(AgentThreadMessage).where(AgentThreadMessage.thread_id == thread.id)
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(AgentThreadMessage.content.ilike(f"%{escaped}%", escape="\\"))
    if before:
        query = query.where(AgentThreadMessage.created_at < before)
    if limit is None:
        return list(
            db.scalars(query.order_by(AgentThreadMessage.created_at, AgentThreadMessage.id))
        )
    # With a limit, return the newest page, still oldest-first for rendering.
    page = db.scalars(
        query.order_by(AgentThreadMessage.created_at.desc(), AgentThreadMessage.id.desc()).limit(
            limit
        )
    )
    return list(reversed(list(page)))


@router.post(
    "/threads/{thread_id}/messages",
    response_model=AgentJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_manager_message(
    thread_id: uuid.UUID,
    payload: AgentThreadMessageCreate,
    db: Session = Depends(get_db),
) -> AgentJob:
    thread = AgentStateService.resolve_thread(db, thread_id)
    source_catalog = None
    if thread.prism_id is not None:
        # The browser never decides whether a private Prism may read a chat.
        # Apply its durable policy before source matching or model evidence.
        from app.services.prism_teams_policy_service import PrismTeamsPolicyService

        _, source_catalog = PrismTeamsPolicyService.allowed_sources(db, thread.prism_id)
    use_thread_as_destination = bool(
        thread.source_external_id
        and thread.source_kind == TeamsReadService.SOURCE_KIND
        and THREAD_DESTINATION_PATTERN.search(payload.content)
        and EXPLICIT_CROSS_SOURCE_READ_PATTERN.search(payload.content)
    )
    resolution = SourceResolutionService.resolve(
        db,
        payload.content,
        constrained_external_id=None if use_thread_as_destination else thread.source_external_id,
        selected_external_id=payload.source_external_id,
        selected_external_ids=payload.source_external_ids,
        catalog=source_catalog,
    )
    sources = resolution.selected_sources or (
        [resolution.selected] if resolution.selected is not None else []
    )
    if resolution.status != "resolved" or not sources:
        raise RuleViolationError("Choose which Teams chat Prism may read for this request")
    source = sources[0]
    scope_mode = {
        "manager_choice": "explicit-set",
        "only_available_source": "auto",
        "auto_recent": "auto",
        "auto_all": "auto",
        "auto_ambiguous": "auto",
        "auto_default": "auto",
    }.get(
        resolution.selection_reason,
        "explicit-set"
        if len(sources) > 1
        else ("person" if source.chat_type == "private" else "chat"),
    )
    resolved_sources = [
        {
            "kind": TeamsReadService.SOURCE_KIND,
            "external_id": item.external_id,
            "label": item.label,
            "metadata": {
                "chat_type": item.chat_type,
                "participants": item.participants,
                "participant_details": [
                    participant.model_dump() for participant in item.participant_details
                ],
                "resolution_rationale": resolution.rationale,
                "excluded_external_ids": resolution.excluded_external_ids,
                "retrieval_limits": resolution.limits,
            },
        }
        for item in sources
    ]
    if use_thread_as_destination and not any(
        item["external_id"] == thread.source_external_id for item in resolved_sources
    ):
        resolved_sources.append(
            {
                "kind": TeamsReadService.SOURCE_KIND,
                "external_id": thread.source_external_id,
                "label": thread.source_label,
                "metadata": {
                    "chat_type": thread.source_metadata.get("chat_type"),
                    "participants": thread.source_metadata.get("participants", []),
                    "resolution_rationale": "The current Teams group is the explicit message destination.",
                    "destination_only": True,
                },
                "selection_reason": "destination",
            }
        )
    job = AgentStateService.create_job(
        db,
        thread_id=thread.id,
        goal=payload.content,
        scope_mode=scope_mode,
        requested_scope={
            "mode": scope_mode,
            "constraint_external_id": (
                None if use_thread_as_destination else thread.source_external_id
            ),
            "destination_external_id": thread.source_external_id
            if use_thread_as_destination
            else None,
            "selected_external_ids": [item.external_id for item in sources],
            "excluded_external_ids": resolution.excluded_external_ids,
            "resolution_rationale": resolution.rationale,
            "limits": resolution.limits,
        },
        resolved_sources=resolved_sources,
        selection_reason=resolution.selection_reason,
    )
    db.add(
        AgentThreadMessage(
            thread_id=thread.id,
            job_id=job.id,
            role="manager",
            content=payload.content,
        )
    )
    thread.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _job(db, job.id)


@router.get(
    "/threads/{thread_id}/jobs",
    response_model=list[AgentJobRead],
    dependencies=[Depends(require_v21)],
)
def list_thread_jobs(thread_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AgentJob]:
    thread = AgentStateService.resolve_thread(db, thread_id)
    return list(
        db.scalars(
            select(AgentJob)
            .options(selectinload(AgentJob.steps), selectinload(AgentJob.sources))
            .where(AgentJob.thread_id == thread.id)
            .order_by(AgentJob.created_at.desc())
            .limit(50)
        )
    )


@router.get(
    "/sources/teams",
    response_model=TeamsChatSourcePage,
    dependencies=[Depends(require_v21)],
)
def list_teams_sources(db: Session = Depends(get_db)) -> TeamsChatSourcePage:
    items = TeamsReadService.list_sources(db)
    return TeamsChatSourcePage(items=items, total=len(items))


@router.post(
    "/sources/teams/resolve",
    response_model=TeamsSourceResolutionRead,
    dependencies=[Depends(require_v21)],
)
def resolve_teams_source(
    payload: TeamsSourceResolutionRequest, db: Session = Depends(get_db)
) -> TeamsSourceResolutionRead:
    return SourceResolutionService.resolve(
        db,
        payload.goal,
        constrained_external_id=payload.constrained_external_id,
        selected_external_id=payload.selected_external_id,
        selected_external_ids=payload.selected_external_ids,
    )


@router.put(
    "/threads/{thread_id}/source/teams",
    response_model=AgentThreadRead,
    dependencies=[Depends(require_v21)],
)
def select_teams_source(
    thread_id: uuid.UUID, payload: TeamsChatSelection, db: Session = Depends(get_db)
) -> AgentThread:
    thread = AgentStateService.resolve_thread(db, thread_id)
    return TeamsReadService.select_source(db, thread.id, payload.external_id)


@router.delete(
    "/threads/{thread_id}/source/teams",
    response_model=AgentThreadRead,
    dependencies=[Depends(require_v21)],
)
def clear_teams_source(thread_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentThread:
    thread = AgentStateService.resolve_thread(db, thread_id)
    return TeamsReadService.clear_source(db, thread.id)


@router.post(
    "/threads/{thread_id}/jobs",
    response_model=AgentJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_job(
    thread_id: uuid.UUID, payload: AgentJobCreate, db: Session = Depends(get_db)
) -> AgentJob:
    thread = AgentStateService.resolve_thread(db, thread_id)
    job = AgentStateService.create_job(
        db,
        thread_id=thread.id,
        goal=payload.goal,
        scope_mode="chat" if thread.source_external_id else "auto",
        requested_scope={
            "source_kind": thread.source_kind,
            "external_id": thread.source_external_id,
            "label": thread.source_label,
        }
        if thread.source_external_id
        else {},
    )
    return _job(db, job.id)


def _job(db: Session, job_id: uuid.UUID) -> AgentJob:
    job = db.scalar(
        select(AgentJob)
        .options(selectinload(AgentJob.steps), selectinload(AgentJob.sources))
        .where(AgentJob.id == job_id)
    )
    if job is None:
        from app.services.errors import NotFoundError

        raise NotFoundError("Agent job was not found")
    return job


@router.get("/jobs/{job_id}", response_model=AgentJobRead, dependencies=[Depends(require_v21)])
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentJob:
    return _job(db, job_id)


@router.post(
    "/jobs/{job_id}/recover",
    response_model=AgentJobRead,
    dependencies=[Depends(require_v21)],
)
def recover_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentJob:
    AgentRecoveryService.recover(db, job_id)
    return _job(db, job_id)


@router.post(
    "/jobs/{job_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v21)],
)
def record_job_feedback(
    job_id: uuid.UUID, payload: AgentFeedbackCreate, db: Session = Depends(get_db)
) -> None:
    if db.get(AgentJob, job_id) is None:
        from app.services.errors import NotFoundError

        raise NotFoundError("Agent job was not found")
    db.add(
        AgentFeedbackEvent(job_id=job_id, event_type=payload.event_type, details=payload.details)
    )
    db.commit()


@router.post(
    "/jobs/{job_id}/evidence/sync",
    response_model=TeamsEvidenceSyncRead,
    dependencies=[Depends(require_v21)],
)
def sync_job_evidence(job_id: uuid.UUID, db: Session = Depends(get_db)) -> TeamsEvidenceSyncRead:
    return TeamsReadService.sync_job_evidence(db, job_id)


@router.get(
    "/jobs/{job_id}/evidence",
    response_model=list[AgentEvidenceRead],
    dependencies=[Depends(require_v21)],
)
def list_job_evidence(job_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AgentEvidenceRead]:
    return TeamsReadService.evidence(db, job_id)


@router.post(
    "/jobs/{job_id}/review",
    response_model=AgentConversationReviewRead,
    dependencies=[Depends(require_v21)],
)
def review_job_conversation(
    job_id: uuid.UUID, db: Session = Depends(get_db)
) -> AgentConversationReviewRead:
    return ConversationReviewService.review(db, job_id)


@router.get(
    "/jobs/{job_id}/review",
    response_model=AgentConversationReviewRead,
    dependencies=[Depends(require_v21)],
)
def get_job_conversation_review(
    job_id: uuid.UUID, db: Session = Depends(get_db)
) -> AgentConversationReviewRead:
    return ConversationReviewService.get(db, job_id)


@router.post(
    "/jobs/{job_id}/transition",
    response_model=AgentJobRead,
    dependencies=[Depends(require_v21)],
)
def transition_job(
    job_id: uuid.UUID, payload: AgentJobTransition, db: Session = Depends(get_db)
) -> AgentJob:
    AgentStateService.transition_job(
        db,
        job_id,
        target=payload.target,
        expected_version=payload.expected_version,
        safe_error_code=payload.safe_error_code,
        safe_error_detail=payload.safe_error_detail,
    )
    if payload.target == AgentJobState.CANCELLED:
        db.add(AgentFeedbackEvent(job_id=job_id, event_type="job_cancelled", details={}))
        db.commit()
    return _job(db, job_id)


@router.post(
    "/jobs/{job_id}/steps",
    response_model=AgentStepRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def append_step(job_id: uuid.UUID, payload: AgentStepCreate, db: Session = Depends(get_db)):
    return AgentStateService.append_step(db, job_id=job_id, kind=payload.kind, label=payload.label)


@router.post(
    "/steps/{step_id}/transition",
    response_model=AgentStepRead,
    dependencies=[Depends(require_v21)],
)
def transition_step(
    step_id: uuid.UUID, payload: AgentStepTransition, db: Session = Depends(get_db)
):
    return AgentStateService.transition_step(
        db,
        step_id,
        target=payload.target,
        safe_error_code=payload.safe_error_code,
        safe_error_detail=payload.safe_error_detail,
    )


@router.post(
    "/jobs/{job_id}/proposals",
    response_model=ActionProposalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def create_proposal(
    job_id: uuid.UUID, payload: ActionProposalCreate, db: Session = Depends(get_db)
):
    return AgentStateService.create_proposal(db, job_id=job_id, **payload.model_dump())


def _expire_stale_prism_draft(db: Session, proposal_id: uuid.UUID) -> None:
    """Proposals prepared from a Prism update expire when their Prism, agreement, or evidence changed."""

    from app.services.prism_draft_service import PrismDraftService

    PrismDraftService.invalidate_if_stale(db, proposal_id)


@router.post(
    "/proposals/{proposal_id}/revisions",
    response_model=ActionProposalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def revise_proposal(
    proposal_id: uuid.UUID, payload: ActionProposalRevise, db: Session = Depends(get_db)
):
    _expire_stale_prism_draft(db, proposal_id)
    return AgentStateService.revise_proposal(
        db, proposal_id, body=payload.body, reason=payload.reason
    )


@router.post(
    "/proposals/{proposal_id}/decision",
    response_model=ApprovalDecisionRead,
    dependencies=[Depends(require_v21)],
)
def decide_proposal(
    proposal_id: uuid.UUID, payload: ApprovalDecisionCreate, db: Session = Depends(get_db)
):
    _expire_stale_prism_draft(db, proposal_id)
    decision = AgentStateService.decide_proposal(
        db,
        proposal_id,
        decision=payload.decision,
        manager_identity="local_manager",
        expected_revision=payload.expected_revision,
        expected_payload_hash=payload.expected_payload_hash,
        reason=payload.reason,
    )
    proposal = db.get(ActionProposal, proposal_id)
    if proposal and proposal.plan_id:
        CoordinatedActionService.refresh_state(db, proposal.plan_id)
    return decision


@router.get(
    "/plans/{plan_id}",
    response_model=AgentActionPlanRead,
    dependencies=[Depends(require_v21)],
)
def get_action_plan(plan_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentActionPlanRead:
    return CoordinatedActionService.get(db, plan_id)


@router.post(
    "/plans/{plan_id}/approve-all",
    response_model=AgentActionPlanRead,
    dependencies=[Depends(require_v21)],
)
def approve_action_plan(
    plan_id: uuid.UUID, payload: BulkApprovalCreate, db: Session = Depends(get_db)
) -> AgentActionPlanRead:
    for plan_proposal_id in db.scalars(
        select(ActionProposal.id).where(ActionProposal.plan_id == plan_id)
    ).all():
        _expire_stale_prism_draft(db, plan_proposal_id)
    return CoordinatedActionService.approve_all(db, plan_id, payload)


@router.post(
    "/proposals/{proposal_id}/execution",
    response_model=ToolExecutionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v21)],
)
def begin_execution(proposal_id: uuid.UUID, db: Session = Depends(get_db)):
    _expire_stale_prism_draft(db, proposal_id)
    return ApprovedTeamsExecutionService.execute(db, proposal_id)
