from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_v21 import AgentJob, ToolExecution
from app.models.enums import AgentJobState, ToolExecutionState
from app.services.agent_state_service import AgentStateService
from app.services.conversation_review_service import ConversationReviewService
from app.services.errors import ConflictError, NotFoundError
from app.services.teams_read_service import TeamsReadService

logger = logging.getLogger(__name__)


class AgentRecoveryService:
    """Manager-triggered recovery that never replays an external write."""

    @staticmethod
    def recover(db: Session, job_id: uuid.UUID) -> AgentJob:
        job = db.get(AgentJob, job_id)
        if job is None:
            raise NotFoundError("Agent job was not found")
        logger.info("v21_recovery_requested job_id=%s state=%s", job.id, job.state.value)

        if job.state == AgentJobState.QUEUED:
            TeamsReadService.sync_job_evidence(db, job.id)
            ConversationReviewService.review(db, job.id)
            db.expire_all()
            recovered = db.get(AgentJob, job.id)
            if recovered is None:
                raise NotFoundError("Agent job was not found after recovery")
            logger.info("v21_recovery_completed job_id=%s state=%s", job.id, recovered.state.value)
            return recovered

        if job.state in {AgentJobState.RESEARCHING, AgentJobState.PLANNING}:
            job.state = AgentJobState.FAILED
            job.version += 1
            job.completed_at = datetime.now(timezone.utc)
            job.safe_error_code = "interrupted_before_write"
            job.safe_error_detail = "Review work was interrupted. Retry creates a fresh safe job."
            db.commit()
            db.refresh(job)
            return job

        if job.state == AgentJobState.EXECUTING:
            execution = db.scalar(
                select(ToolExecution)
                .where(
                    ToolExecution.job_id == job.id,
                    ToolExecution.state == ToolExecutionState.RUNNING,
                )
                .order_by(ToolExecution.created_at.desc())
                .limit(1)
            )
            if execution is None:
                raise ConflictError("No interrupted execution was found")
            execution = AgentStateService.finish_execution(
                db,
                execution.id,
                state=ToolExecutionState.UNCERTAIN,
                safe_error_code="reconciliation_required",
                safe_error_detail=(
                    "Prism restarted during delivery. The message was not retried to avoid a duplicate."
                ),
            )
            db.expire_all()
            job = db.get(AgentJob, execution.job_id)
            if job is None:
                raise NotFoundError("Agent job was not found after recovery")
            job.state = AgentJobState.FAILED
            job.version += 1
            job.completed_at = datetime.now(timezone.utc)
            job.safe_error_code = execution.safe_error_code
            job.safe_error_detail = execution.safe_error_detail
            db.commit()
            db.refresh(job)
            return job

        if job.state in {
            AgentJobState.WAITING_FOR_APPROVAL,
            AgentJobState.COMPLETED,
            AgentJobState.FAILED,
            AgentJobState.CANCELLED,
        }:
            return job
        raise ConflictError("This job has no safe recovery action")
