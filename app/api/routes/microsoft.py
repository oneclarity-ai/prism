from __future__ import annotations

import logging
import uuid
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.agents.management_agent import ManagementAgent
from app.db.session import SessionLocal, get_db
from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, MessageDirection
from app.models.llm_usage import LLMUsage
from app.models.message import Message
from app.schemas.microsoft import (
    AgentDecisionRunRead,
    AutomationRunRead,
    AutomationStart,
    DailyDigestRead,
    DirectorySyncResult,
    MicrosoftStatusRead,
    SubscriptionRenewalResult,
)
from app.services.automation_service import DailyAutomationService
from app.services.errors import DomainError
from app.services.microsoft_service import (
    MicrosoftDirectoryService,
    MicrosoftGraphClient,
    MicrosoftService,
)

router = APIRouter(prefix="/api/v1/microsoft", tags=["Microsoft Teams automation"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=MicrosoftStatusRead)
def microsoft_status(db: Session = Depends(get_db)) -> MicrosoftStatusRead:
    """Show local Microsoft connection and Teams listener state without exposing credentials."""

    return MicrosoftService.status(db)


@router.get("/auth/start", include_in_schema=False)
def start_microsoft_authentication(db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect the manager to the single-tenant Microsoft authorization page using PKCE."""

    return RedirectResponse(MicrosoftGraphClient.authorization_url(db), status_code=302)


@router.get("/auth/callback", include_in_schema=False)
def complete_microsoft_authentication(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Finish Microsoft sign-in and return the browser to the local dashboard."""

    try:
        if error:
            raise DomainError(error_description or error)
        if not code or not state:
            raise DomainError("Microsoft did not return a valid authorization response")
        MicrosoftGraphClient.complete_authorization(db, code=code, state=state)
        return RedirectResponse("/dashboard/?microsoft=connected", status_code=303)
    except DomainError as exc:
        return RedirectResponse(
            "/dashboard/?" + urlencode({"microsoft_error": exc.detail}), status_code=303
        )


@router.post("/directory/sync", response_model=DirectorySyncResult)
def sync_active_organization_users(db: Session = Depends(get_db)) -> DirectorySyncResult:
    """Import or update active directory users in the organization without messaging them."""

    return MicrosoftDirectoryService.sync_active_users(db)


@router.post("/automation/start", response_model=AutomationRunRead)
def start_teams_automation(
    payload: Optional[AutomationStart] = None, db: Session = Depends(get_db)
) -> AutomationRunRead:
    """Send the initial check-in from the manager's Teams account to selected managed employees."""

    return MicrosoftService.start_automation(db, payload or AutomationStart())


@router.post("/automation/stop", response_model=AutomationRunRead)
def stop_teams_automation(db: Session = Depends(get_db)) -> AutomationRunRead:
    """Stop the current run and delete its active Microsoft reply listeners."""

    return MicrosoftService.stop_automation(db)


@router.post("/automation/renew-listener", response_model=SubscriptionRenewalResult)
def renew_teams_listener(db: Session = Depends(get_db)) -> SubscriptionRenewalResult:
    """Renew current Graph reply listeners; V1 needs this manually about once per hour."""

    return MicrosoftService.renew_listener(db)


@router.post("/automation/run-cycle")
def run_manager_automation_cycle(
    force: bool = False,
    include_later_day_actions: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Run the approved V1 daily automation cycle once; force is for controlled testing."""

    return DailyAutomationService.run_cycle(
        db, force=force, include_later_day_actions=include_later_day_actions
    )


@router.post("/automation/send-digest-email")
def send_manager_digest_email(db: Session = Depends(get_db)) -> dict[str, object]:
    """Send an on-demand manager digest to the connected Microsoft account's mailbox."""

    recipient = DailyAutomationService.send_daily_digest_email(db)
    return {"sent": 1, "recipient": recipient}


@router.get("/automation/digests", response_model=list[DailyDigestRead])
def list_persisted_daily_digests(
    limit: int = 30, db: Session = Depends(get_db)
) -> list[DailyDigestRead]:
    """Return the exact daily digest copies previously sent through Teams."""

    return [
        DailyDigestRead(
            id=action.id,
            digest_date=action.executed_at.date(),
            status=action.status,
            sent_at=action.executed_at,
            content=action.message.content,
        )
        for action in DailyAutomationService.list_daily_digests(db, limit=min(max(limit, 1), 100))
        if action.message is not None
    ]


def process_reply_in_background(message_id: str) -> None:
    """Run after Graph has received its fast 202 response, using a fresh DB session."""

    db = SessionLocal()
    try:
        ManagementAgent.process_message(db, message_id)
    except Exception:
        logger.exception("teams_reply_processing_failed message_id=%s", message_id)
    finally:
        db.close()


@router.post("/agent/process-pending")
def process_pending_teams_replies(
    force: bool = False, db: Session = Depends(get_db)
) -> dict[str, int]:
    """Process replies saved before Azure OpenAI was configured or before this workflow existed."""

    retryable = [AgentRunStatus.PENDING, AgentRunStatus.FAILED]
    if force:
        retryable.append(AgentRunStatus.SKIPPED)
    message_ids = list(
        db.scalars(
            select(Message.id)
            .outerjoin(AgentRun, AgentRun.inbound_message_id == Message.id)
            .where(
                Message.direction == MessageDirection.INBOUND,
                or_(AgentRun.id.is_(None), AgentRun.status.in_(retryable)),
            )
            .order_by(Message.created_at)
            .limit(100)
        )
    )
    processed = 0
    for message_id in message_ids:
        result = ManagementAgent.process_message(db, str(message_id), retry_skipped=force)
        if result is not None:
            processed += 1
    return {"processed": processed}


@router.get("/agent/runs", response_model=list[AgentDecisionRunRead])
def list_agent_decision_runs(
    message_id: Optional[uuid.UUID] = None,
    status: Optional[AgentRunStatus] = None,
    include_context: bool = False,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[AgentDecisionRunRead]:
    """Inspect structured decisions and their measured model usage; no chain-of-thought."""

    query = select(AgentRun).order_by(AgentRun.created_at.desc(), AgentRun.id).limit(limit)
    if message_id:
        query = query.where(AgentRun.inbound_message_id == message_id)
    if status is not None:
        query = query.where(AgentRun.status == status)
    runs = list(db.scalars(query))
    if not runs:
        return []
    usage_rows = list(
        db.scalars(
            select(LLMUsage).where(
                LLMUsage.message_id.in_([run.inbound_message_id for run in runs])
            )
        )
    )
    by_message = {}
    for usage in usage_rows:
        by_message.setdefault(usage.message_id, []).append(usage)
    output = []
    for run in runs:
        usage = by_message.get(run.inbound_message_id, [])
        priced = [
            item.estimated_total_cost_usd
            for item in usage
            if item.estimated_total_cost_usd is not None
        ]
        context = run.context_json or {}
        output.append(
            AgentDecisionRunRead(
                id=run.id,
                inbound_message_id=run.inbound_message_id,
                source_employee_id=run.source_employee_id,
                status=run.status,
                model_deployment=run.model_deployment,
                state_applied=run.state_applied,
                needs_manager_review=run.needs_manager_review,
                failure_reason=run.failure_reason,
                processed_at=run.processed_at,
                created_at=run.created_at,
                decision=run.decision_json,
                context_source_ids=context.get("context_source_ids", []),
                context=context if include_context else None,
                llm_calls=len(usage),
                input_tokens=sum(item.input_tokens or 0 for item in usage),
                cached_input_tokens=sum(item.cached_input_tokens or 0 for item in usage),
                output_tokens=sum(item.output_tokens or 0 for item in usage),
                estimated_cost_usd=sum(priced),
                unpriced_calls=len(usage) - len(priced),
                latency_ms=sum(item.latency_ms for item in usage),
                attempt_count=run.attempt_count,
                last_attempt_at=run.last_attempt_at,
                next_retry_at=run.next_retry_at,
                policy_version=run.policy_version,
            )
        )
    return output


@router.post("/teams/webhook", include_in_schema=False)
async def receive_teams_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Response:
    """Validate Graph callbacks, save replies, then queue the bounded management analysis."""

    validation_token = request.query_params.get("validationToken")
    if validation_token is not None:
        return PlainTextResponse(validation_token)
    payload = await request.json()
    notifications = payload.get("value", []) if isinstance(payload, dict) else []
    if isinstance(notifications, list):
        for notification in notifications:
            if isinstance(notification, dict):
                message_id = await run_in_threadpool(
                    MicrosoftService.process_webhook_notification, db, notification
                )
                if message_id is not None:
                    background_tasks.add_task(process_reply_in_background, message_id)
    return Response(status_code=202)
