"""Feature-gated Prism v2.2 API boundary.

This router is deliberately small in Phase 0. Keeping the boundary separate from
the v2.1 agent routes prevents unfinished multi-Prism behavior from changing the
working manager-agent journey.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.agent_v21 import AgentJob, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import (
    Prism,
    PrismLifecycleEvent,
    PrismRun,
    PrismTeamsSourcePolicy,
)
from app.schemas.agent_v21 import AgentJobRead, AgentThreadMessageCreate
from app.schemas.prism_v22 import (
    PrismAgreementConfirm,
    PrismAgreementConfirmationRead,
    PrismAgreementRead,
    PrismBudgetUpdate,
    PrismConversationRead,
    PrismCreate,
    PrismFeedbackCreate,
    PrismFoundationRead,
    PrismIncidentHistoryRead,
    PrismLifecycleCommand,
    PrismLifecycleEventRead,
    PrismMemoryCreate,
    PrismNotificationClaimRead,
    PrismNotificationResult,
    PrismNotificationSettingRead,
    PrismNotificationSettingUpdate,
    PrismObservationDraftCreate,
    PrismObservationDraftRead,
    PrismObservationPage,
    PrismObservationsRead,
    PrismOnboardingAnswerInput,
    PrismOnboardingSessionRead,
    PrismPresenceBeat,
    PrismRead,
    PrismRunPage,
    PrismRunRead,
    PrismSignalMute,
    PrismTeamsEventsPage,
    PrismTeamsSourcePolicyRead,
    PrismTeamsSourcePolicyUpdate,
    PrismTeamsSyncRead,
    PrismTriggerPolicyRead,
    PrismTriggerPolicyUpdate,
    PrismUpdate,
    PrismUpdateSummaryRead,
)
from app.services.agent_preference_service import AgentPreferenceService
from app.services.prism_agreement_service import PrismAgreementService
from app.services.prism_conversation_service import PrismConversationService
from app.services.prism_draft_service import PrismDraftService
from app.services.prism_health_service import PrismHealthService
from app.services.prism_incident_service import PrismIncidentService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.prism_migration_service import PrismMigrationService
from app.services.prism_notification_service import PrismNotificationService
from app.services.prism_observation_service import PrismObservationService
from app.services.prism_onboarding_service import PrismOnboardingService
from app.services.prism_run_service import PrismRunService
from app.services.prism_teams_policy_service import PrismTeamsPolicyService
from app.services.prism_tuning_service import PrismTuningService

router = APIRouter(prefix="/api/v2/prisms", tags=["Prism v2.2 workspace"])


def require_v22() -> None:
    if not get_settings().prism_v22_enabled:
        raise HTTPException(status_code=404, detail="Prism v2.2 is not enabled")


@router.get("/foundation", response_model=PrismFoundationRead, dependencies=[Depends(require_v22)])
def foundation() -> PrismFoundationRead:
    """Describe the currently available v2.2 capability boundary."""

    settings = get_settings()
    return PrismFoundationRead(
        enabled=True,
        release="v2.2",
        phase=13,
        single_executive_mode=settings.prism_v22_single_executive_mode,
        capabilities=[
            "feature-isolated multi-Prism release boundary",
            "durable private Prism identities and lifecycle audit",
            "private Prism directory, creation, and archive workflow",
            "resumable role-aware onboarding with validated answers",
            "reviewable working agreements with explicit activation",
            "isolated continuing conversation and memory for every active Prism",
            "durable Teams monitoring scope with local incremental activity reads",
            "durable local monitoring schedules and lease-claimed runs",
            "evidence-linked proactive Teams recommendations",
            "durable unread updates and open-page browser notifications",
            "conservative cross-Prism incident grouping with audited evolution",
            "approval-gated Teams drafts prepared from proactive updates",
            "feedback, signal tuning, run budgets, health diagnostics, and retention",
            "v2.1 conversation migration and operator recovery",
            "v2.1 regression compatibility",
        ],
        excluded_capabilities=[
            "autonomous or approval-gated v2.2 actions",
        ],
    )


@router.get(
    "/updates/summary",
    response_model=list[PrismUpdateSummaryRead],
    dependencies=[Depends(require_v22)],
)
def update_summaries(db: Session = Depends(get_db)) -> list[PrismUpdateSummaryRead]:
    """Per-Prism unread and urgent counters derived from stored observations."""

    return PrismNotificationService.update_summaries(db)


@router.post(
    "/notifications/presence",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def notification_presence(payload: PrismPresenceBeat, db: Session = Depends(get_db)) -> None:
    PrismNotificationService.heartbeat(db, payload.client_id)


@router.post(
    "/notifications/claim",
    response_model=PrismNotificationClaimRead,
    dependencies=[Depends(require_v22)],
)
def claim_notification(
    payload: PrismPresenceBeat, db: Session = Depends(get_db)
) -> PrismNotificationClaimRead:
    """Hand one eligible notification to one live page; each is claimed at most once."""

    return PrismNotificationClaimRead(
        notification=PrismNotificationService.claim_next(db, payload.client_id)
    )


@router.post(
    "/notifications/{notification_id}/result",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def report_notification(
    notification_id: uuid.UUID, payload: PrismNotificationResult, db: Session = Depends(get_db)
) -> None:
    PrismNotificationService.report(db, notification_id, payload.client_id, payload.result)


@router.post("/migrate-legacy", response_model=None, dependencies=[Depends(require_v22)])
def migrate_legacy_conversation(db: Session = Depends(get_db)) -> dict:
    """Adopt the v2.1 conversation as an Executive Assistant Prism. Safe to repeat."""

    return PrismMigrationService.adopt_legacy_conversation(db)


@router.get("", response_model=list[PrismRead], dependencies=[Depends(require_v22)])
def list_prisms(
    include_archived: bool = Query(default=False), db: Session = Depends(get_db)
) -> list[Prism]:
    return PrismLifecycleService.list_prisms(db, include_archived=include_archived)


@router.post(
    "",
    response_model=PrismRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v22)],
)
def create_prism(payload: PrismCreate, db: Session = Depends(get_db)) -> Prism:
    """Create a durable draft. Dynamic onboarding arrives in Phase 3."""

    if get_settings().prism_v22_single_executive_mode:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Single Executive Assistant mode allows one Prism only",
        )
    return PrismLifecycleService.create(db, payload)


@router.get("/{prism_id}", response_model=PrismRead, dependencies=[Depends(require_v22)])
def get_prism(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> Prism:
    return PrismLifecycleService.get(db, prism_id)


@router.patch("/{prism_id}", response_model=PrismRead, dependencies=[Depends(require_v22)])
def update_prism(prism_id: uuid.UUID, payload: PrismUpdate, db: Session = Depends(get_db)) -> Prism:
    return PrismLifecycleService.update(db, prism_id, payload)


@router.get(
    "/{prism_id}/lifecycle",
    response_model=list[PrismLifecycleEventRead],
    dependencies=[Depends(require_v22)],
)
def list_lifecycle_events(
    prism_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[PrismLifecycleEvent]:
    return PrismLifecycleService.events(db, prism_id)


@router.post("/{prism_id}/archive", response_model=PrismRead, dependencies=[Depends(require_v22)])
def archive_prism(
    prism_id: uuid.UUID, payload: PrismLifecycleCommand, db: Session = Depends(get_db)
) -> Prism:
    return PrismLifecycleService.transition(
        db,
        prism_id,
        target=PrismLifecycleState.ARCHIVED,
        expected_lifecycle_version=payload.expected_lifecycle_version,
        event_type="archived",
        reason=payload.reason,
    )


@router.post(
    "/{prism_id}/onboarding/start",
    response_model=PrismOnboardingSessionRead,
    dependencies=[Depends(require_v22)],
)
def start_onboarding(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Create a durable, role-aware question set or resume the existing one."""

    return PrismOnboardingService.start(db, prism_id)


@router.get(
    "/{prism_id}/onboarding",
    response_model=PrismOnboardingSessionRead,
    dependencies=[Depends(require_v22)],
)
def get_onboarding(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return PrismOnboardingService.get(db, prism_id)


@router.post(
    "/{prism_id}/onboarding/questions/{question_id}/answer",
    response_model=PrismOnboardingSessionRead,
    dependencies=[Depends(require_v22)],
)
def answer_onboarding_question(
    prism_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: PrismOnboardingAnswerInput,
    db: Session = Depends(get_db),
) -> dict:
    return PrismOnboardingService.answer(db, prism_id, question_id, payload)


@router.get(
    "/{prism_id}/agreement",
    response_model=PrismAgreementRead,
    dependencies=[Depends(require_v22)],
)
def get_working_agreement(prism_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the immutable preview created from completed, explicit onboarding answers."""

    return PrismAgreementService.get_or_create(db, prism_id)


@router.post(
    "/{prism_id}/agreement/confirm",
    response_model=PrismAgreementConfirmationRead,
    dependencies=[Depends(require_v22)],
)
def confirm_working_agreement(
    prism_id: uuid.UUID, payload: PrismAgreementConfirm, db: Session = Depends(get_db)
) -> dict:
    agreement, prism = PrismAgreementService.confirm(db, prism_id, payload)
    return {"agreement": agreement, "prism": prism}


@router.get(
    "/{prism_id}/conversation",
    response_model=PrismConversationRead,
    dependencies=[Depends(require_v22)],
)
def get_prism_conversation(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Return only the selected Prism's canonical conversation and memories."""

    PrismDraftService.invalidate_for_prism(db, prism_id)

    _, thread = PrismConversationService.canonical_thread(db, prism_id)
    messages = list(
        db.scalars(
            select(AgentThreadMessage)
            .where(AgentThreadMessage.thread_id == thread.id)
            .order_by(AgentThreadMessage.created_at, AgentThreadMessage.id)
            .limit(200)
        )
    )
    jobs = list(
        db.scalars(
            select(AgentJob)
            .options(selectinload(AgentJob.steps), selectinload(AgentJob.sources))
            .where(AgentJob.thread_id == thread.id)
            .order_by(AgentJob.created_at.desc())
            .limit(50)
        )
    )
    return {
        "prism_id": prism_id,
        "thread": thread,
        "messages": messages,
        "jobs": jobs,
        "preferences": AgentPreferenceService.list_for_prism(db, prism_id),
    }


@router.post(
    "/{prism_id}/conversation/messages",
    response_model=AgentJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v22)],
)
def create_prism_message(
    prism_id: uuid.UUID,
    payload: AgentThreadMessageCreate,
    db: Session = Depends(get_db),
) -> AgentJob:
    """Create work only in the selected Prism's server-resolved conversation."""

    _, thread = PrismConversationService.canonical_thread(db, prism_id)
    # Reuse the proven v2.1 evidence → review → approval workflow.  The
    # browser never supplies a thread id, so cross-Prism routing is impossible.
    from app.api.routes.agent_v21 import create_manager_message

    return create_manager_message(thread.id, payload, db)


@router.get(
    "/{prism_id}/teams-policy",
    response_model=PrismTeamsSourcePolicyRead,
    dependencies=[Depends(require_v22)],
)
def get_teams_source_policy(
    prism_id: uuid.UUID, db: Session = Depends(get_db)
) -> PrismTeamsSourcePolicy:
    """Return the private Prism's durable Teams monitoring boundary."""

    return PrismTeamsPolicyService.get(db, prism_id)


@router.put(
    "/{prism_id}/teams-policy",
    response_model=PrismTeamsSourcePolicyRead,
    dependencies=[Depends(require_v22)],
)
def update_teams_source_policy(
    prism_id: uuid.UUID,
    payload: PrismTeamsSourcePolicyUpdate,
    db: Session = Depends(get_db),
) -> PrismTeamsSourcePolicy:
    """Save a chat-ID based source restriction after validating current access."""

    return PrismTeamsPolicyService.update(db, prism_id, payload)


@router.post(
    "/{prism_id}/teams-activity/sync",
    response_model=PrismTeamsSyncRead,
    dependencies=[Depends(require_v22)],
)
def sync_teams_activity(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> PrismTeamsSyncRead:
    """Run one safe, bounded localhost Teams poll for this Prism."""

    return PrismTeamsPolicyService.sync(db, prism_id)


@router.get(
    "/{prism_id}/teams-activity",
    response_model=PrismTeamsEventsPage,
    dependencies=[Depends(require_v22)],
)
def list_teams_activity(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> PrismTeamsEventsPage:
    events, total = PrismTeamsPolicyService.events(db, prism_id)
    return PrismTeamsEventsPage(items=events, total=total)


@router.get(
    "/{prism_id}/trigger-policy",
    response_model=PrismTriggerPolicyRead,
    dependencies=[Depends(require_v22)],
)
def get_trigger_policy(
    prism_id: uuid.UUID, db: Session = Depends(get_db)
) -> PrismTriggerPolicyRead:
    return PrismRunService.policy_read(db, prism_id)


@router.put(
    "/{prism_id}/trigger-policy",
    response_model=PrismTriggerPolicyRead,
    dependencies=[Depends(require_v22)],
)
def update_trigger_policy(
    prism_id: uuid.UUID,
    payload: PrismTriggerPolicyUpdate,
    db: Session = Depends(get_db),
) -> PrismTriggerPolicyRead:
    return PrismRunService.update_policy(db, prism_id, payload)


@router.get(
    "/{prism_id}/runs",
    response_model=PrismRunPage,
    dependencies=[Depends(require_v22)],
)
def list_prism_runs(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> PrismRunPage:
    runs, total = PrismRunService.list_runs(db, prism_id)
    return PrismRunPage(items=runs, total=total)


@router.get(
    "/{prism_id}/observations",
    response_model=PrismObservationPage,
    dependencies=[Depends(require_v22)],
)
def list_prism_observations(
    prism_id: uuid.UUID, db: Session = Depends(get_db)
) -> PrismObservationPage:
    """Return stored recommendations; this endpoint never creates a message draft."""

    observations, total = PrismObservationService.list(db, prism_id)
    return PrismObservationPage(items=observations, total=total)


@router.post(
    "/{prism_id}/observations/read",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def mark_observations_read(
    prism_id: uuid.UUID, payload: PrismObservationsRead, db: Session = Depends(get_db)
) -> None:
    """Mark listed observations (or all, when none are listed) read for this Prism."""

    PrismNotificationService.mark_read(db, prism_id, payload.observation_ids)


@router.get(
    "/{prism_id}/observations/{observation_id}/incident",
    response_model=PrismIncidentHistoryRead,
    dependencies=[Depends(require_v22)],
)
def observation_incident(
    prism_id: uuid.UUID, observation_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Explain why this observation was (or was not) grouped with others."""

    return PrismIncidentService.history(db, prism_id, observation_id)


@router.post(
    "/{prism_id}/observations/{observation_id}/incident/split",
    response_model=PrismIncidentHistoryRead,
    dependencies=[Depends(require_v22)],
)
def split_observation_incident(
    prism_id: uuid.UUID, observation_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Undo a false grouping; observations are kept."""

    PrismIncidentService.split(db, prism_id, observation_id, datetime.now(timezone.utc))
    return PrismIncidentService.history(db, prism_id, observation_id)


@router.post(
    "/{prism_id}/observations/{observation_id}/drafts",
    response_model=AgentJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v22)],
)
def draft_from_observation(
    prism_id: uuid.UUID,
    observation_id: uuid.UUID,
    payload: PrismObservationDraftCreate,
    db: Session = Depends(get_db),
) -> AgentJob:
    """Prepare a Teams draft for approval; this never approves or sends anything."""

    return PrismDraftService.create(
        db,
        prism_id,
        observation_id,
        request_id=payload.request_id,
        instruction=payload.instruction,
    )


@router.get(
    "/{prism_id}/observations/{observation_id}/drafts",
    response_model=list[PrismObservationDraftRead],
    dependencies=[Depends(require_v22)],
)
def list_observation_drafts(
    prism_id: uuid.UUID, observation_id: uuid.UUID, db: Session = Depends(get_db)
):
    return PrismDraftService.list_for_observation(db, prism_id, observation_id)


@router.post(
    "/{prism_id}/observations/{observation_id}/feedback",
    response_model=None,
    dependencies=[Depends(require_v22)],
)
def observation_feedback(
    prism_id: uuid.UUID,
    observation_id: uuid.UUID,
    payload: PrismFeedbackCreate,
    db: Session = Depends(get_db),
) -> dict:
    """Record a judgment for this Prism only; it never changes another Prism."""

    return {
        "feedback_kinds": PrismTuningService.record_feedback(
            db, prism_id, observation_id, payload.kind
        )
    }


@router.get("/{prism_id}/tuning", response_model=None, dependencies=[Depends(require_v22)])
def get_tuning(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return {
        "signals": PrismTuningService.tuning(db, prism_id),
        "budget": PrismTuningService.budget(db, prism_id),
    }


@router.put(
    "/{prism_id}/tuning/signals/{signal_type}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def set_signal_muted(
    prism_id: uuid.UUID, signal_type: str, payload: PrismSignalMute, db: Session = Depends(get_db)
) -> None:
    """Confirm or undo a signal choice; mandatory safety signals are refused."""

    PrismTuningService.set_muted(db, prism_id, signal_type, payload.muted)


@router.put(
    "/{prism_id}/budget",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def update_budget(
    prism_id: uuid.UUID, payload: PrismBudgetUpdate, db: Session = Depends(get_db)
) -> None:
    PrismTuningService.update_budget(db, prism_id, payload.model_dump())


@router.post(
    "/{prism_id}/migration-review/acknowledge",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_v22)],
)
def acknowledge_migration_review(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """The user has reviewed the migrated agreement; automatic monitoring may now run."""

    PrismLifecycleService.get(db, prism_id)
    PrismMigrationService.acknowledge_review(db, prism_id)


@router.get("/{prism_id}/health", response_model=None, dependencies=[Depends(require_v22)])
def prism_health(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Why this Prism is quiet, delayed, or failing; counts only, no message text or secrets."""

    return PrismHealthService.status(db, prism_id)


@router.get(
    "/{prism_id}/notification-settings",
    response_model=PrismNotificationSettingRead,
    dependencies=[Depends(require_v22)],
)
def get_notification_settings(prism_id: uuid.UUID, db: Session = Depends(get_db)):
    return PrismNotificationService.get_setting(db, prism_id)


@router.put(
    "/{prism_id}/notification-settings",
    response_model=PrismNotificationSettingRead,
    dependencies=[Depends(require_v22)],
)
def update_notification_settings(
    prism_id: uuid.UUID, payload: PrismNotificationSettingUpdate, db: Session = Depends(get_db)
):
    return PrismNotificationService.update_setting(db, prism_id, payload)


@router.post(
    "/{prism_id}/runs/manual",
    response_model=PrismRunRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v22)],
)
def run_prism_monitoring_now(prism_id: uuid.UUID, db: Session = Depends(get_db)) -> PrismRun:
    """Run a one-off, approval-free Teams read under the existing source policy."""

    return PrismRunService.run_manual(db, prism_id)


@router.post(
    "/{prism_id}/memory",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_v22)],
)
def remember_for_prism(
    prism_id: uuid.UUID, payload: PrismMemoryCreate, db: Session = Depends(get_db)
) -> dict:
    """Store an explicit working preference in this Prism only."""

    _, thread = PrismConversationService.canonical_thread(db, prism_id)
    preference = AgentPreferenceService.remember_for_prism(
        db, prism_id=prism_id, thread_id=thread.id, instruction=payload.instruction
    )
    return {"id": str(preference.id), "instruction": preference.instruction}
