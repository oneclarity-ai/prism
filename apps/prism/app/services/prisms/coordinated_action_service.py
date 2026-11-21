from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ActionProposalState, ApprovalDecisionType
from app.models.prisms.agent_v21 import (
    ActionProposal,
    AgentActionPlan,
    AgentJob,
    AgentJobSource,
    ToolExecution,
)
from app.schemas.prisms.agent_review import ReviewProposedAction
from app.schemas.prisms.agent_v21 import (
    ActionProposalRead,
    AgentActionPlanRead,
    BulkApprovalCreate,
    PlannedActionRead,
    ToolExecutionRead,
)
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.prisms.agent_state_service import AgentStateService


class CoordinatedActionService:
    @staticmethod
    def create(
        db: Session,
        *,
        job: AgentJob,
        summary: str,
        actions: list[ReviewProposedAction],
    ) -> AgentActionPlan:
        if db.scalar(select(AgentActionPlan).where(AgentActionPlan.job_id == job.id)):
            raise ConflictError("This job already has an action plan")
        sources = CoordinatedActionService.validate(db, job, actions)
        destinations = [item.destination_source_id for item in actions]

        logical_ids = {source_id: uuid.uuid4() for source_id in destinations}
        plan = AgentActionPlan(
            job_id=job.id,
            summary=summary.strip() or f"Coordinate {len(actions)} Teams messages",
            state="pending",
            plan_metadata={
                "destination_count": len(actions),
                "destination_source_ids": destinations,
            },
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        for action in sorted(actions, key=lambda item: item.sequence):
            source = sources[action.destination_source_id]
            AgentStateService.create_proposal(
                db,
                job_id=job.id,
                plan_id=plan.id,
                logical_action_id=logical_ids[action.destination_source_id],
                sequence=action.sequence,
                depends_on_logical_action_ids=[
                    str(logical_ids[source_id]) for source_id in action.depends_on_source_ids
                ],
                action="teams.send_chat_message",
                destination={
                    "kind": "teams_chat",
                    "chat_id": source.external_id,
                    "label": source.label,
                    "participants": source.source_metadata.get("participants", []),
                },
                body=action.body,
                reason=action.reason,
                evidence_ids=action.evidence_ids,
            )
        db.refresh(plan)
        return plan

    @staticmethod
    def validate(
        db: Session, job: AgentJob, actions: list[ReviewProposedAction]
    ) -> dict[str, AgentJobSource]:
        if not actions:
            raise RuleViolationError("A coordinated action plan requires at least one action")
        sources = {
            item.external_id: item
            for item in db.scalars(select(AgentJobSource).where(AgentJobSource.job_id == job.id))
        }
        destinations = [item.destination_source_id for item in actions]
        if len(destinations) != len(set(destinations)):
            raise RuleViolationError(
                "A coordinated plan can contain only one action per destination"
            )
        if set(destinations) - set(sources):
            raise RuleViolationError("The action plan contains an unauthorized Teams destination")
        sequences = [item.sequence for item in actions]
        if len(sequences) != len(set(sequences)):
            raise RuleViolationError("Every planned action must have a unique sequence")
        CoordinatedActionService._validate_dependencies(actions)
        return sources

    @staticmethod
    def get(db: Session, plan_id: uuid.UUID) -> AgentActionPlanRead:
        plan = db.get(AgentActionPlan, plan_id)
        if plan is None:
            raise NotFoundError("Action plan was not found")
        return CoordinatedActionService._read(db, plan)

    @staticmethod
    def for_job(db: Session, job_id: uuid.UUID) -> AgentActionPlanRead | None:
        plan = db.scalar(select(AgentActionPlan).where(AgentActionPlan.job_id == job_id))
        return CoordinatedActionService._read(db, plan) if plan else None

    @staticmethod
    def approve_all(
        db: Session, plan_id: uuid.UUID, payload: BulkApprovalCreate
    ) -> AgentActionPlanRead:
        plan = db.get(AgentActionPlan, plan_id)
        if plan is None:
            raise NotFoundError("Action plan was not found")
        latest = CoordinatedActionService._latest_proposals(db, plan.id)
        pending = {item.id: item for item in latest if item.state == ActionProposalState.PENDING}
        supplied = {item.proposal_id: item for item in payload.items}
        if set(supplied) != set(pending):
            raise ConflictError(
                "Bulk approval must include every currently pending action shown in the plan"
            )
        for proposal_id, proposal in pending.items():
            item = supplied[proposal_id]
            if (
                item.expected_revision != proposal.revision
                or item.expected_payload_hash != proposal.payload_hash
            ):
                raise ConflictError("An action changed; review the full plan before approving")
        for proposal_id, proposal in pending.items():
            item = supplied[proposal_id]
            AgentStateService.decide_proposal(
                db,
                proposal_id,
                decision=ApprovalDecisionType.APPROVED,
                manager_identity="local_manager",
                expected_revision=item.expected_revision,
                expected_payload_hash=item.expected_payload_hash,
            )
        CoordinatedActionService.refresh_state(db, plan.id)
        return CoordinatedActionService.get(db, plan.id)

    @staticmethod
    def refresh_state(db: Session, plan_id: uuid.UUID) -> None:
        plan = db.get(AgentActionPlan, plan_id)
        if plan is None:
            return
        latest = CoordinatedActionService._latest_proposals(db, plan.id)
        states = {item.state for item in latest}
        if states & {
            ActionProposalState.PENDING,
            ActionProposalState.APPROVED,
            ActionProposalState.EXECUTING,
        }:
            plan.state = "in_progress" if states != {ActionProposalState.PENDING} else "pending"
        else:
            failed = sum(item.state == ActionProposalState.FAILED for item in latest)
            succeeded = sum(item.state == ActionProposalState.EXECUTED for item in latest)
            if failed and succeeded:
                plan.state = "partially_failed"
            elif failed:
                plan.state = "failed"
            else:
                plan.state = "completed"
        db.commit()

    @staticmethod
    def dependencies_succeeded(db: Session, proposal: ActionProposal) -> bool:
        if not proposal.depends_on_logical_action_ids:
            return True
        dependencies = list(
            db.scalars(
                select(ActionProposal).where(
                    ActionProposal.logical_action_id.in_(
                        [uuid.UUID(item) for item in proposal.depends_on_logical_action_ids]
                    )
                )
            )
        )
        latest = {
            item.logical_action_id: item
            for item in sorted(dependencies, key=lambda item: item.revision)
        }
        if len(latest) != len(proposal.depends_on_logical_action_ids):
            return False
        return all(item.state == ActionProposalState.EXECUTED for item in latest.values())

    @staticmethod
    def _read(db: Session, plan: AgentActionPlan) -> AgentActionPlanRead:
        latest = CoordinatedActionService._latest_proposals(db, plan.id)
        proposal_ids = [item.id for item in latest]
        executions = {
            item.proposal_id: item
            for item in db.scalars(
                select(ToolExecution)
                .where(ToolExecution.proposal_id.in_(proposal_ids))
                .order_by(ToolExecution.created_at)
            )
        }
        return AgentActionPlanRead.model_validate(plan).model_copy(
            update={
                "actions": [
                    PlannedActionRead(
                        proposal=ActionProposalRead.model_validate(item),
                        execution=ToolExecutionRead.model_validate(executions[item.id])
                        if item.id in executions
                        else None,
                    )
                    for item in latest
                ]
            }
        )

    @staticmethod
    def _latest_proposals(db: Session, plan_id: uuid.UUID) -> list[ActionProposal]:
        proposals = list(
            db.scalars(
                select(ActionProposal)
                .where(ActionProposal.plan_id == plan_id)
                .order_by(ActionProposal.sequence, ActionProposal.revision)
            )
        )
        latest: dict[uuid.UUID, ActionProposal] = {}
        for proposal in proposals:
            latest[proposal.logical_action_id] = proposal
        return sorted(latest.values(), key=lambda item: (item.sequence, item.id))

    @staticmethod
    def _validate_dependencies(actions: list[ReviewProposedAction]) -> None:
        destinations = {item.destination_source_id for item in actions}
        graph = {item.destination_source_id: set(item.depends_on_source_ids) for item in actions}
        for destination, dependencies in graph.items():
            if destination in dependencies or dependencies - destinations:
                raise RuleViolationError(
                    "Action dependencies must reference another planned action"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise RuleViolationError("Action dependencies cannot contain a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for destination in graph:
            visit(destination)
