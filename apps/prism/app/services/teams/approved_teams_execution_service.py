from __future__ import annotations

import html
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ActionProposalState,
    AgentJobState,
    ApprovalDecisionType,
    ToolExecutionState,
)
from app.models.prisms.agent_v21 import (
    ActionProposal,
    AgentFeedbackEvent,
    AgentJob,
    AgentThreadMessage,
    ToolExecution,
)
from app.services.errors import ConflictError, DomainError, RuleViolationError
from app.services.prisms.agent_state_service import AgentStateService, canonical_payload_hash
from app.services.prisms.coordinated_action_service import CoordinatedActionService
from app.services.teams.microsoft_service import MicrosoftGraphClient, MicrosoftService

logger = logging.getLogger(__name__)


class ApprovedTeamsExecutionService:
    """The only v2.1 boundary allowed to turn an approved draft into a Graph write."""

    TOOL_NAME = "microsoft_graph.teams.send_chat_message"
    ACTION = "teams.send_chat_message"
    MANAGER_IDENTITY = "local_manager"

    @staticmethod
    def _signature(db: Session, job: AgentJob, connection) -> str | None:
        """Which Prism wrote this message, so the recipient sees "Sent by Yash's QA Tester Prism"."""
        from app.models.prisms.agent_v21 import AgentThread
        from app.models.prisms.prism_v22 import Prism

        thread = db.get(AgentThread, job.thread_id)
        prism = db.get(Prism, thread.prism_id) if thread is not None and thread.prism_id else None
        if prism is None:
            return None
        return MicrosoftService.prism_signature(
            getattr(connection, "display_name", None), prism.name
        )

    @staticmethod
    def execute(db: Session, proposal_id: uuid.UUID) -> ToolExecution:
        proposal = db.scalar(
            select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
        )
        if proposal is None:
            from app.services.errors import NotFoundError

            raise NotFoundError("Action proposal was not found")
        existing = db.scalar(
            select(ToolExecution).where(ToolExecution.idempotency_key == f"proposal:{proposal.id}")
        )
        if existing is not None:
            logger.info(
                "v21_execution_idempotent proposal_id=%s execution_id=%s state=%s",
                proposal.id,
                existing.id,
                existing.state.value,
            )
            return existing
        ApprovedTeamsExecutionService._validate(db, proposal)

        execution, created = AgentStateService.acquire_execution(
            db,
            proposal.id,
            manager_identity=ApprovedTeamsExecutionService.MANAGER_IDENTITY,
            tool_name=ApprovedTeamsExecutionService.TOOL_NAME,
        )
        if not created:
            return execution

        job = db.get(AgentJob, proposal.job_id)
        if job is None:
            raise ConflictError("The approved action no longer has a job")
        if job.state != AgentJobState.WAITING_FOR_APPROVAL:
            return ApprovedTeamsExecutionService._fail(
                db, execution, "invalid_job_state", "The approved action is no longer sendable"
            )
        job.state = AgentJobState.EXECUTING
        job.version += 1
        db.commit()
        logger.info(
            "v21_graph_send_started job_id=%s proposal_id=%s execution_id=%s",
            job.id,
            proposal.id,
            execution.id,
        )

        try:
            connection = MicrosoftService.get_connection(db)
            graph = MicrosoftGraphClient(db, connection)
            destination_chat_id = str(proposal.destination.get("chat_id") or "")
            result = graph.send_chat_message(
                destination_chat_id,
                proposal.body,
                ApprovedTeamsExecutionService._signature(db, job, connection),
            )
            message_id = result.get("id") if isinstance(result, dict) else None
            if not isinstance(message_id, str) or not message_id:
                raise RuleViolationError("Microsoft did not return a Teams message identifier")
            return ApprovedTeamsExecutionService._succeed(
                db,
                execution,
                message_id=message_id,
                sent_at=result.get("createdDateTime"),
                reconciled=False,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            try:
                match = ApprovedTeamsExecutionService._reconcile(
                    graph,
                    connection.microsoft_user_id,
                    destination_chat_id,
                    proposal.body,
                    not_before=(execution.started_at or datetime.now(timezone.utc))
                    - timedelta(minutes=2),
                )
            except Exception:
                match = None
            if match:
                return ApprovedTeamsExecutionService._succeed(
                    db,
                    execution,
                    message_id=str(match["id"]),
                    sent_at=match.get("createdDateTime"),
                    reconciled=True,
                )
            return ApprovedTeamsExecutionService._uncertain(db, execution)
        except DomainError as exc:
            return ApprovedTeamsExecutionService._fail(db, execution, exc.code, exc.detail)
        except Exception:
            return ApprovedTeamsExecutionService._fail(
                db, execution, "teams_send_failed", "The Teams message was not delivered"
            )

    @staticmethod
    def _validate(db: Session, proposal: ActionProposal) -> None:
        latest = [
            item
            for item in proposal.job.proposals
            if item.logical_action_id == proposal.logical_action_id
        ]
        if latest and max(item.revision for item in latest) != proposal.revision:
            raise ConflictError("A newer proposal revision must be reviewed")
        approval = proposal.approval
        if (
            proposal.state != ActionProposalState.APPROVED
            or approval is None
            or approval.decision != ApprovalDecisionType.APPROVED
            or approval.manager_identity != ApprovedTeamsExecutionService.MANAGER_IDENTITY
            or approval.proposal_revision != proposal.revision
        ):
            raise ConflictError("Current manager approval is required before sending")
        if proposal.expires_at and proposal.expires_at <= datetime.now(timezone.utc):
            raise ConflictError("This approval has expired; create and review a new draft")
        job = proposal.job
        destination = proposal.destination
        expected_hash = canonical_payload_hash(
            action=proposal.action, destination=destination, body=proposal.body
        )
        if expected_hash != proposal.payload_hash or approval.payload_hash != expected_hash:
            raise ConflictError("The approved message changed; review it again")
        authorized_destination = next(
            (
                item
                for item in job.sources
                if item.source_kind == "teams_chat"
                and item.external_id == destination.get("chat_id")
            ),
            None,
        )
        if (
            proposal.action != ApprovedTeamsExecutionService.ACTION
            or destination.get("kind") != "teams_chat"
            or authorized_destination is None
        ):
            raise ConflictError("The approved Teams destination is not authorized for this job")
        if not CoordinatedActionService.dependencies_succeeded(db, proposal):
            raise ConflictError("A prerequisite action has not been delivered successfully")

    @staticmethod
    def _succeed(
        db: Session,
        execution: ToolExecution,
        *,
        message_id: str,
        sent_at: Any,
        reconciled: bool,
    ) -> ToolExecution:
        execution = AgentStateService.finish_execution(
            db,
            execution.id,
            state=ToolExecutionState.SUCCEEDED,
            safe_result={
                "external_message_id": message_id,
                "sent_at": sent_at,
                "reconciled": reconciled,
            },
        )
        ApprovedTeamsExecutionService._finish_job(db, execution, success=True)
        return execution

    @staticmethod
    def _fail(db: Session, execution: ToolExecution, code: str, detail: str) -> ToolExecution:
        execution = AgentStateService.finish_execution(
            db,
            execution.id,
            state=ToolExecutionState.FAILED,
            safe_error_code=code,
            safe_error_detail=detail,
        )
        ApprovedTeamsExecutionService._finish_job(db, execution, success=False)
        return execution

    @staticmethod
    def _uncertain(db: Session, execution: ToolExecution) -> ToolExecution:
        execution = AgentStateService.finish_execution(
            db,
            execution.id,
            state=ToolExecutionState.UNCERTAIN,
            safe_error_code="reconciliation_required",
            safe_error_detail=(
                "Microsoft delivery could not be confirmed. Prism did not retry, to avoid a duplicate."
            ),
        )
        ApprovedTeamsExecutionService._finish_job(db, execution, success=False)
        return execution

    @staticmethod
    def _finish_job(db: Session, execution: ToolExecution, *, success: bool) -> None:
        job = db.get(AgentJob, execution.job_id)
        if job is None:
            return
        proposal = execution.proposal
        plan_id = proposal.plan_id if proposal else None
        if plan_id:
            CoordinatedActionService.refresh_state(db, plan_id)
            plan = CoordinatedActionService.get(db, plan_id)
            active_states = {"pending", "approved", "executing"}
            has_active = any(
                action.proposal.state.value in active_states for action in plan.actions
            )
            job.state = (
                AgentJobState.WAITING_FOR_APPROVAL if has_active else AgentJobState.COMPLETED
            )
            job.completed_at = None if has_active else datetime.now(timezone.utc)
            job.safe_error_code = None
            job.safe_error_detail = None
        else:
            job.state = AgentJobState.COMPLETED if success else AgentJobState.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.safe_error_code = None if success else execution.safe_error_code
            job.safe_error_detail = None if success else execution.safe_error_detail
        job.version += 1
        if success:
            destination_label = (
                proposal.destination.get("label") if proposal else None
            ) or job.source_label
            db.add(
                AgentThreadMessage(
                    thread_id=job.thread_id,
                    job_id=job.id,
                    role="assistant",
                    content=f"Delivered to {destination_label or 'the selected Teams chat'}.",
                    message_metadata={
                        "kind": "teams_delivery",
                        "execution_id": str(execution.id),
                        "external_message_id": execution.safe_result["external_message_id"],
                        "proposal_id": str(execution.proposal_id),
                    },
                )
            )
        db.add(
            AgentFeedbackEvent(
                job_id=job.id,
                proposal_id=execution.proposal_id,
                execution_id=execution.id,
                event_type="delivery_succeeded" if success else "delivery_failed",
                details={"error_code": execution.safe_error_code} if not success else {},
            )
        )
        db.commit()
        logger.info(
            "v21_graph_send_finished job_id=%s execution_id=%s state=%s error_code=%s",
            job.id,
            execution.id,
            execution.state.value,
            execution.safe_error_code,
        )

    @staticmethod
    def _reconcile(
        graph,
        manager_id: str,
        chat_id: str,
        body: str,
        *,
        not_before: datetime,
    ) -> dict[str, Any] | None:
        expected = ApprovedTeamsExecutionService._plain(body)
        for message in graph.list_chat_messages(chat_id, limit=20):
            sender = ((message.get("from") or {}).get("user") or {}).get("id")
            content = (message.get("body") or {}).get("content") or ""
            sent_at = ApprovedTeamsExecutionService._timestamp(message.get("createdDateTime"))
            if (
                sender == manager_id
                and message.get("id")
                and sent_at is not None
                and sent_at >= not_before
                and ApprovedTeamsExecutionService._plain(content) == expected
            ):
                return message
        return None

    @staticmethod
    def _plain(value: str) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
