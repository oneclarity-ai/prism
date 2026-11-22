from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import ToolExecutionState
from app.models.prisms.agent_v21 import ActionProposal, AgentThread
from app.schemas.prisms.agent_review import ReviewProposedAction
from app.schemas.prisms.agent_v21 import BulkApprovalCreate, BulkApprovalItem
from app.services.errors import RuleViolationError
from app.services.prisms.agent_state_service import AgentStateService
from app.services.prisms.coordinated_action_service import CoordinatedActionService


def action(destination: str, sequence: int, *, dependencies: list[str] | None = None):
    return ReviewProposedAction(
        destination_source_id=destination,
        body=f"Message for {destination}",
        reason="Manager requested a coordinated follow-up",
        evidence_ids=[f"evidence-{sequence}"],
        sequence=sequence,
        depends_on_source_ids=dependencies or [],
    )


def test_actions_are_independently_versioned_approved_and_completed() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Coordinated actions")
            thread_id = thread.id
            job = AgentStateService.create_job(
                db,
                thread_id=thread.id,
                goal="Follow up with Parv, then update Meera",
                resolved_sources=[
                    {"kind": "teams_chat", "external_id": "chat-parv", "label": "Parv"},
                    {"kind": "teams_chat", "external_id": "chat-meera", "label": "Meera"},
                ],
            )
            plan = CoordinatedActionService.create(
                db,
                job=job,
                summary="Coordinate the release follow-up",
                actions=[
                    action("chat-parv", 1),
                    action("chat-meera", 2, dependencies=["chat-parv"]),
                ],
            )
            view = CoordinatedActionService.get(db, plan.id)
            first, second = [item.proposal for item in view.actions]
            revised = AgentStateService.revise_proposal(
                db, first.id, body="Updated message for Parv"
            )
            current = CoordinatedActionService.get(db, plan.id)
            assert current.actions[0].proposal.id == revised.id
            assert current.actions[0].proposal.revision == 2
            assert current.actions[1].proposal.id == second.id
            assert current.actions[1].proposal.revision == 1

            approved = CoordinatedActionService.approve_all(
                db,
                plan.id,
                BulkApprovalCreate(
                    items=[
                        BulkApprovalItem(
                            proposal_id=item.proposal.id,
                            expected_revision=item.proposal.revision,
                            expected_payload_hash=item.proposal.payload_hash,
                        )
                        for item in current.actions
                    ]
                ),
            )
            first, second = [item.proposal for item in approved.actions]
            assert all(item.proposal.state.value == "approved" for item in approved.actions)
            assert not CoordinatedActionService.dependencies_succeeded(
                db, db.get(ActionProposal, second.id)
            )

            first_execution = AgentStateService.begin_execution(
                db,
                first.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            repeated = AgentStateService.begin_execution(
                db,
                first.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            assert repeated.id == first_execution.id
            AgentStateService.finish_execution(
                db,
                first_execution.id,
                state=ToolExecutionState.SUCCEEDED,
                safe_result={"external_message_id": "message-parv"},
            )
            assert CoordinatedActionService.dependencies_succeeded(
                db, db.get(ActionProposal, second.id)
            )
            second_execution = AgentStateService.begin_execution(
                db,
                second.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            AgentStateService.finish_execution(
                db,
                second_execution.id,
                state=ToolExecutionState.SUCCEEDED,
                safe_result={"external_message_id": "message-meera"},
            )
            CoordinatedActionService.refresh_state(db, plan.id)
            assert CoordinatedActionService.get(db, plan.id).state == "completed"
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                thread = db.get(AgentThread, thread_id)
                if thread is not None:
                    db.delete(thread)
                    db.commit()


def test_hidden_recipient_and_dependency_cycle_are_rejected() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Plan validation")
            thread_id = thread.id
            job = AgentStateService.create_job(
                db,
                thread_id=thread.id,
                goal="Coordinate updates",
                resolved_sources=[
                    {"kind": "teams_chat", "external_id": "chat-parv", "label": "Parv"},
                    {"kind": "teams_chat", "external_id": "chat-meera", "label": "Meera"},
                ],
            )
            with pytest.raises(RuleViolationError, match="unauthorized"):
                CoordinatedActionService.validate(db, job, [action("hidden-chat", 1)])
            with pytest.raises(RuleViolationError, match="cycle"):
                CoordinatedActionService.validate(
                    db,
                    job,
                    [
                        action("chat-parv", 1, dependencies=["chat-meera"]),
                        action("chat-meera", 2, dependencies=["chat-parv"]),
                    ],
                )
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                thread = db.get(AgentThread, thread_id)
                if thread is not None:
                    db.delete(thread)
                    db.commit()
