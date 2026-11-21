from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.agent_v21 import (
    ActionProposal,
    AgentFeedbackEvent,
    AgentJob,
    AgentJobSource,
    AgentStep,
    AgentThread,
    AgentThreadAlias,
    ApprovalDecision,
    ToolExecution,
)
from app.models.enums import (
    ActionProposalState,
    AgentJobState,
    AgentStepState,
    ApprovalDecisionType,
    ToolExecutionState,
)
from app.services.errors import ConflictError, NotFoundError, RuleViolationError

JOB_TRANSITIONS: dict[AgentJobState, set[AgentJobState]] = {
    AgentJobState.QUEUED: {
        AgentJobState.RESEARCHING,
        AgentJobState.FAILED,
        AgentJobState.CANCELLED,
    },
    AgentJobState.RESEARCHING: {
        AgentJobState.PLANNING,
        AgentJobState.WAITING_FOR_APPROVAL,
        AgentJobState.COMPLETED,
        AgentJobState.FAILED,
        AgentJobState.CANCELLED,
    },
    AgentJobState.PLANNING: {
        AgentJobState.WAITING_FOR_APPROVAL,
        AgentJobState.COMPLETED,
        AgentJobState.FAILED,
        AgentJobState.CANCELLED,
    },
    AgentJobState.WAITING_FOR_APPROVAL: {
        AgentJobState.EXECUTING,
        AgentJobState.FAILED,
        AgentJobState.CANCELLED,
    },
    AgentJobState.EXECUTING: {
        AgentJobState.WAITING_FOR_APPROVAL,
        AgentJobState.COMPLETED,
        AgentJobState.FAILED,
    },
    AgentJobState.COMPLETED: set(),
    AgentJobState.FAILED: set(),
    AgentJobState.CANCELLED: set(),
}

STEP_TRANSITIONS: dict[AgentStepState, set[AgentStepState]] = {
    AgentStepState.QUEUED: {AgentStepState.RUNNING, AgentStepState.CANCELLED},
    AgentStepState.RUNNING: {
        AgentStepState.COMPLETED,
        AgentStepState.FAILED,
        AgentStepState.CANCELLED,
    },
    AgentStepState.COMPLETED: set(),
    AgentStepState.FAILED: set(),
    AgentStepState.CANCELLED: set(),
}


def canonical_payload_hash(*, action: str, destination: dict, body: str) -> str:
    canonical = json.dumps(
        {"action": action, "destination": destination, "body": body},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentStateService:
    @staticmethod
    def canonical_thread(db: Session) -> AgentThread:
        # The original v2.1 conversation is the only canonical thread without
        # a Prism owner. Never let a newly-created v2.2 Prism steal it.
        # A conversation adopted by the migrated Executive Assistant Prism is still the
        # v2.1 conversation, so turning v2.2 off never strands or forks its history.
        thread = db.scalar(
            select(AgentThread)
            .where(
                AgentThread.is_canonical.is_(True),
                or_(
                    AgentThread.prism_id.is_(None),
                    AgentThread.source_metadata["migrated_from_v21"].as_boolean().is_(True),
                ),
            )
            .order_by(AgentThread.prism_id.is_(None).desc())
        )
        if thread is not None:
            return thread
        thread = AgentThread(title="Prism", is_canonical=True, source_metadata={})
        db.add(thread)
        db.commit()
        db.refresh(thread)
        db.add(AgentThreadAlias(legacy_thread_id=thread.id, canonical_thread_id=thread.id))
        db.commit()
        return thread

    @staticmethod
    def resolve_thread(db: Session, thread_id: uuid.UUID) -> AgentThread:
        thread = db.get(AgentThread, thread_id)
        if thread is not None:
            return thread
        alias = db.get(AgentThreadAlias, thread_id)
        if alias is None:
            raise NotFoundError("Agent conversation was not found")
        canonical = db.get(AgentThread, alias.canonical_thread_id)
        if canonical is None:
            raise NotFoundError("Agent conversation was not found")
        return canonical

    @staticmethod
    def create_thread(
        db: Session,
        *,
        title: str,
        source_kind: str | None = None,
        source_external_id: str | None = None,
        source_label: str | None = None,
        source_metadata: dict | None = None,
    ) -> AgentThread:
        thread = AgentThread(
            title=title.strip(),
            source_kind=source_kind,
            source_external_id=source_external_id,
            source_label=source_label,
            source_metadata=source_metadata or {},
        )
        if not thread.title:
            raise RuleViolationError("Agent thread title is required")
        db.add(thread)
        db.commit()
        db.refresh(thread)
        return thread

    @staticmethod
    def create_job(
        db: Session,
        *,
        thread_id: uuid.UUID,
        goal: str,
        scope_mode: str = "chat",
        requested_scope: dict | None = None,
        resolved_source: dict | None = None,
        resolved_sources: list[dict] | None = None,
        selection_reason: str = "explicit",
    ) -> AgentJob:
        thread = AgentStateService.resolve_thread(db, thread_id)
        sources = resolved_sources or ([resolved_source] if resolved_source else [])
        if not sources:
            sources = [
                {
                    "kind": thread.source_kind,
                    "external_id": thread.source_external_id,
                    "label": thread.source_label,
                    "metadata": dict(thread.source_metadata),
                }
            ]
        source = sources[0]
        job = AgentJob(
            thread_id=thread.id,
            goal=goal.strip(),
            state=AgentJobState.QUEUED,
            source_kind=source.get("kind"),
            source_external_id=source.get("external_id"),
            source_label=source.get("label"),
            source_metadata=dict(source.get("metadata") or {}),
            scope_mode=scope_mode,
            requested_scope=requested_scope or {},
        )
        if not job.goal:
            raise RuleViolationError("Agent job goal is required")
        db.add(job)
        for resolved in sources:
            if not resolved.get("kind") or not resolved.get("external_id"):
                continue
            db.add(
                AgentJobSource(
                    job=job,
                    source_kind=resolved["kind"],
                    external_id=resolved["external_id"],
                    label=resolved.get("label"),
                    source_metadata=dict(resolved.get("metadata") or {}),
                    selection_reason=resolved.get("selection_reason", selection_reason),
                )
            )
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def transition_job(
        db: Session,
        job_id: uuid.UUID,
        *,
        target: AgentJobState,
        expected_version: int,
        safe_error_code: str | None = None,
        safe_error_detail: str | None = None,
    ) -> AgentJob:
        job = db.scalar(select(AgentJob).where(AgentJob.id == job_id).with_for_update())
        if job is None:
            raise NotFoundError("Agent job was not found")
        if job.version != expected_version:
            raise ConflictError("Agent job changed; refresh before trying again")
        if target not in JOB_TRANSITIONS[job.state]:
            raise RuleViolationError(f"Illegal agent job transition: {job.state} -> {target}")
        now = datetime.now(timezone.utc)
        if target == AgentJobState.RESEARCHING and job.started_at is None:
            job.started_at = now
        if target in {AgentJobState.COMPLETED, AgentJobState.FAILED, AgentJobState.CANCELLED}:
            job.completed_at = now
        job.state = target
        job.version += 1
        job.safe_error_code = safe_error_code if target == AgentJobState.FAILED else None
        job.safe_error_detail = safe_error_detail if target == AgentJobState.FAILED else None
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def append_step(db: Session, *, job_id: uuid.UUID, kind: str, label: str) -> AgentStep:
        job = db.scalar(select(AgentJob).where(AgentJob.id == job_id).with_for_update())
        if job is None:
            raise NotFoundError("Agent job was not found")
        sequence = (
            int(
                db.scalar(
                    select(func.coalesce(func.max(AgentStep.sequence), 0)).where(
                        AgentStep.job_id == job_id
                    )
                )
                or 0
            )
            + 1
        )
        step = AgentStep(job_id=job_id, sequence=sequence, kind=kind, label=label)
        db.add(step)
        db.commit()
        db.refresh(step)
        return step

    @staticmethod
    def transition_step(
        db: Session,
        step_id: uuid.UUID,
        *,
        target: AgentStepState,
        safe_error_code: str | None = None,
        safe_error_detail: str | None = None,
    ) -> AgentStep:
        step = db.scalar(select(AgentStep).where(AgentStep.id == step_id).with_for_update())
        if step is None:
            raise NotFoundError("Agent step was not found")
        if target not in STEP_TRANSITIONS[step.state]:
            raise RuleViolationError(f"Illegal agent step transition: {step.state} -> {target}")
        now = datetime.now(timezone.utc)
        if target == AgentStepState.RUNNING:
            step.started_at = now
        if target in {AgentStepState.COMPLETED, AgentStepState.FAILED, AgentStepState.CANCELLED}:
            step.completed_at = now
        step.state = target
        step.safe_error_code = safe_error_code if target == AgentStepState.FAILED else None
        step.safe_error_detail = safe_error_detail if target == AgentStepState.FAILED else None
        db.commit()
        db.refresh(step)
        return step

    @staticmethod
    def create_proposal(
        db: Session,
        *,
        job_id: uuid.UUID,
        action: str,
        destination: dict,
        body: str,
        reason: str,
        evidence_ids: list[str] | None = None,
        plan_id: uuid.UUID | None = None,
        sequence: int = 1,
        depends_on_logical_action_ids: list[str] | None = None,
        logical_action_id: uuid.UUID | None = None,
    ) -> ActionProposal:
        if db.get(AgentJob, job_id) is None:
            raise NotFoundError("Agent job was not found")
        clean_body = body.strip()
        if not clean_body:
            raise RuleViolationError("Proposal body is required")
        proposal = ActionProposal(
            job_id=job_id,
            plan_id=plan_id,
            sequence=sequence,
            depends_on_logical_action_ids=depends_on_logical_action_ids or [],
            logical_action_id=logical_action_id or uuid.uuid4(),
            revision=1,
            action=action,
            state=ActionProposalState.PENDING,
            destination=destination,
            body=clean_body,
            reason=reason.strip(),
            evidence_ids=evidence_ids or [],
            payload_hash=canonical_payload_hash(
                action=action, destination=destination, body=clean_body
            ),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        return proposal

    @staticmethod
    def revise_proposal(
        db: Session, proposal_id: uuid.UUID, *, body: str, reason: str | None = None
    ) -> ActionProposal:
        current = db.scalar(
            select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
        )
        if current is None:
            raise NotFoundError("Action proposal was not found")
        latest_revision = db.scalar(
            select(func.max(ActionProposal.revision)).where(
                ActionProposal.logical_action_id == current.logical_action_id
            )
        )
        if current.revision != latest_revision:
            raise ConflictError("Only the latest proposal revision can be edited")
        if current.state in {ActionProposalState.EXECUTING, ActionProposalState.EXECUTED}:
            raise RuleViolationError("An executing or executed proposal cannot be edited")
        clean_body = body.strip()
        if not clean_body:
            raise RuleViolationError("Proposal body is required")
        current.state = ActionProposalState.EXPIRED
        current.version += 1
        revised = ActionProposal(
            job_id=current.job_id,
            plan_id=current.plan_id,
            sequence=current.sequence,
            depends_on_logical_action_ids=current.depends_on_logical_action_ids,
            logical_action_id=current.logical_action_id,
            previous_revision_id=current.id,
            revision=current.revision + 1,
            action=current.action,
            state=ActionProposalState.PENDING,
            destination=current.destination,
            body=clean_body,
            reason=(reason.strip() if reason else current.reason),
            evidence_ids=current.evidence_ids,
            payload_hash=canonical_payload_hash(
                action=current.action, destination=current.destination, body=clean_body
            ),
        )
        db.add(revised)
        db.add(
            AgentFeedbackEvent(
                job_id=current.job_id,
                proposal_id=revised.id,
                event_type="proposal_edited",
                details={"previous_proposal_id": str(current.id)},
            )
        )
        db.commit()
        db.refresh(revised)
        return revised

    @staticmethod
    def decide_proposal(
        db: Session,
        proposal_id: uuid.UUID,
        *,
        decision: ApprovalDecisionType,
        manager_identity: str,
        expected_revision: int,
        expected_payload_hash: str,
        reason: str | None = None,
    ) -> ApprovalDecision:
        proposal = db.scalar(
            select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
        )
        if proposal is None:
            raise NotFoundError("Action proposal was not found")
        existing = db.scalar(
            select(ApprovalDecision).where(ApprovalDecision.proposal_id == proposal_id)
        )
        if existing is not None:
            if (
                existing.decision == decision
                and existing.proposal_revision == expected_revision
                and existing.payload_hash == expected_payload_hash
            ):
                return existing
            raise ConflictError("This proposal already has an approval decision")
        if proposal.state != ActionProposalState.PENDING:
            raise ConflictError("Only a pending proposal can be approved or rejected")
        if proposal.revision != expected_revision or proposal.payload_hash != expected_payload_hash:
            raise ConflictError("Proposal changed; review the current revision before deciding")
        approval = ApprovalDecision(
            proposal=proposal,
            decision=decision,
            proposal_revision=proposal.revision,
            payload_hash=proposal.payload_hash,
            manager_identity=manager_identity,
            reason=reason,
            decided_at=datetime.now(timezone.utc),
        )
        proposal.state = (
            ActionProposalState.APPROVED
            if decision == ApprovalDecisionType.APPROVED
            else ActionProposalState.REJECTED
        )
        proposal.version += 1
        db.add(approval)
        db.add(
            AgentFeedbackEvent(
                job_id=proposal.job_id,
                proposal_id=proposal.id,
                event_type=(
                    "proposal_approved"
                    if decision == ApprovalDecisionType.APPROVED
                    else "proposal_rejected"
                ),
                details={"revision": proposal.revision},
            )
        )
        db.commit()
        db.refresh(approval)
        return approval

    @staticmethod
    def begin_execution(
        db: Session,
        proposal_id: uuid.UUID,
        *,
        manager_identity: str,
        tool_name: str,
    ) -> ToolExecution:
        execution, _created = AgentStateService.acquire_execution(
            db,
            proposal_id,
            manager_identity=manager_identity,
            tool_name=tool_name,
        )
        return execution

    @staticmethod
    def acquire_execution(
        db: Session,
        proposal_id: uuid.UUID,
        *,
        manager_identity: str,
        tool_name: str,
    ) -> tuple[ToolExecution, bool]:
        idempotency_key = f"proposal:{proposal_id}"
        proposal = db.scalar(
            select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
        )
        if proposal is None:
            raise NotFoundError("Action proposal was not found")
        existing = db.scalar(
            select(ToolExecution).where(ToolExecution.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        approval = proposal.approval
        if (
            proposal.state != ActionProposalState.APPROVED
            or approval is None
            or approval.decision != ApprovalDecisionType.APPROVED
            or approval.manager_identity != manager_identity
            or approval.proposal_revision != proposal.revision
            or approval.payload_hash != proposal.payload_hash
        ):
            raise ConflictError("Proposal approval is missing or stale")
        execution = ToolExecution(
            job_id=proposal.job_id,
            proposal_id=proposal.id,
            tool_name=tool_name,
            operation="write",
            state=ToolExecutionState.RUNNING,
            idempotency_key=idempotency_key,
            request_hash=proposal.payload_hash,
            started_at=datetime.now(timezone.utc),
        )
        proposal.state = ActionProposalState.EXECUTING
        proposal.version += 1
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution, True

    @staticmethod
    def finish_execution(
        db: Session,
        execution_id: uuid.UUID,
        *,
        state: ToolExecutionState,
        safe_result: dict[str, Any] | None = None,
        safe_error_code: str | None = None,
        safe_error_detail: str | None = None,
    ) -> ToolExecution:
        if state not in {
            ToolExecutionState.SUCCEEDED,
            ToolExecutionState.FAILED,
            ToolExecutionState.UNCERTAIN,
        }:
            raise RuleViolationError("Execution can finish only as succeeded, failed, or uncertain")
        execution = db.scalar(
            select(ToolExecution).where(ToolExecution.id == execution_id).with_for_update()
        )
        if execution is None:
            raise NotFoundError("Tool execution was not found")
        if execution.state != ToolExecutionState.RUNNING:
            if execution.state == state:
                return execution
            raise ConflictError("Tool execution already has an authoritative result")
        execution.state = state
        execution.safe_result = safe_result
        execution.safe_error_code = safe_error_code
        execution.safe_error_detail = safe_error_detail
        execution.completed_at = datetime.now(timezone.utc)
        if execution.proposal is not None:
            execution.proposal.state = (
                ActionProposalState.EXECUTED
                if state == ToolExecutionState.SUCCEEDED
                else ActionProposalState.FAILED
            )
            execution.proposal.version += 1
        db.commit()
        db.refresh(execution)
        return execution
