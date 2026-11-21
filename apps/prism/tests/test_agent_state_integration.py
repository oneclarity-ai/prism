from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, func, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import (
    ActionProposalState,
    AgentJobState,
    ApprovalDecisionType,
    ToolExecutionState,
)
from app.models.prisms.agent_v21 import AgentThread, ApprovalDecision, ToolExecution
from app.services.errors import ConflictError, RuleViolationError
from app.services.prisms.agent_recovery_service import AgentRecoveryService
from app.services.prisms.agent_state_service import AgentStateService


def test_revision_approval_and_execution_are_exact_and_idempotent() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Integration thread")
            thread_id = thread.id
            job = AgentStateService.create_job(db, thread_id=thread.id, goal="Draft a reply")
            job = AgentStateService.transition_job(
                db,
                job.id,
                target=AgentJobState.RESEARCHING,
                expected_version=job.version,
            )
            job = AgentStateService.transition_job(
                db,
                job.id,
                target=AgentJobState.PLANNING,
                expected_version=job.version,
            )
            proposal = AgentStateService.create_proposal(
                db,
                job_id=job.id,
                action="teams.send_chat_message",
                destination={"chat_id": "chat-1", "recipients": ["person-1"]},
                body="Original body",
                reason="A reply is needed",
                evidence_ids=["message-1"],
            )
            original_hash = proposal.payload_hash
            revised = AgentStateService.revise_proposal(db, proposal.id, body="Exact approved body")
            db.refresh(proposal)
            assert proposal.state == ActionProposalState.EXPIRED
            assert revised.revision == 2
            assert revised.payload_hash != original_hash

            with pytest.raises(ConflictError):
                AgentStateService.decide_proposal(
                    db,
                    revised.id,
                    decision=ApprovalDecisionType.APPROVED,
                    manager_identity="local_manager",
                    expected_revision=1,
                    expected_payload_hash=original_hash,
                )
            db.rollback()

            approval = AgentStateService.decide_proposal(
                db,
                revised.id,
                decision=ApprovalDecisionType.APPROVED,
                manager_identity="local_manager",
                expected_revision=2,
                expected_payload_hash=revised.payload_hash,
            )
            repeated = AgentStateService.decide_proposal(
                db,
                revised.id,
                decision=ApprovalDecisionType.APPROVED,
                manager_identity="local_manager",
                expected_revision=2,
                expected_payload_hash=revised.payload_hash,
            )
            assert repeated.id == approval.id

            execution = AgentStateService.begin_execution(
                db,
                revised.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            repeated_execution = AgentStateService.begin_execution(
                db,
                revised.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            assert repeated_execution.id == execution.id
            assert (
                db.scalar(
                    select(func.count(ToolExecution.id)).where(
                        ToolExecution.proposal_id == revised.id
                    )
                )
                == 1
            )
            finished = AgentStateService.finish_execution(
                db,
                execution.id,
                state=ToolExecutionState.SUCCEEDED,
                safe_result={"delivered": True},
            )
            assert finished.state == ToolExecutionState.SUCCEEDED
            assert finished.proposal.state == ActionProposalState.EXECUTED
            assert (
                db.scalar(
                    select(ApprovalDecision).where(ApprovalDecision.proposal_id == revised.id)
                )
                is not None
            )
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                thread = db.get(AgentThread, thread_id)
                if thread is not None:
                    db.delete(thread)
                    db.commit()


def test_illegal_job_transition_and_stale_version_are_rejected() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Transition test")
            thread_id = thread.id
            job = AgentStateService.create_job(db, thread_id=thread.id, goal="Test transitions")
            with pytest.raises(RuleViolationError):
                AgentStateService.transition_job(
                    db,
                    job.id,
                    target=AgentJobState.COMPLETED,
                    expected_version=job.version,
                )
            db.rollback()
            moved = AgentStateService.transition_job(
                db,
                job.id,
                target=AgentJobState.RESEARCHING,
                expected_version=job.version,
            )
            with pytest.raises(ConflictError):
                AgentStateService.transition_job(
                    db,
                    job.id,
                    target=AgentJobState.PLANNING,
                    expected_version=moved.version - 1,
                )
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                db.execute(delete(AgentThread).where(AgentThread.id == thread_id))
                db.commit()


def test_recovery_fails_interrupted_read_work_and_never_replays_write() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Recovery safety")
            thread_id = thread.id
            read_job = AgentStateService.create_job(
                db, thread_id=thread.id, goal="Interrupted read"
            )
            read_job = AgentStateService.transition_job(
                db,
                read_job.id,
                target=AgentJobState.RESEARCHING,
                expected_version=read_job.version,
            )
            recovered_read = AgentRecoveryService.recover(db, read_job.id)
            assert recovered_read.state == AgentJobState.FAILED
            assert recovered_read.safe_error_code == "interrupted_before_write"

            write_job = AgentStateService.create_job(
                db, thread_id=thread.id, goal="Interrupted send"
            )
            write_job = AgentStateService.transition_job(
                db,
                write_job.id,
                target=AgentJobState.RESEARCHING,
                expected_version=write_job.version,
            )
            write_job = AgentStateService.transition_job(
                db,
                write_job.id,
                target=AgentJobState.PLANNING,
                expected_version=write_job.version,
            )
            write_job = AgentStateService.transition_job(
                db,
                write_job.id,
                target=AgentJobState.WAITING_FOR_APPROVAL,
                expected_version=write_job.version,
            )
            proposal = AgentStateService.create_proposal(
                db,
                job_id=write_job.id,
                action="teams.send_chat_message",
                destination={"kind": "teams_chat", "chat_id": "chat-recovery"},
                body="Do not replay me",
                reason="Recovery test",
            )
            AgentStateService.decide_proposal(
                db,
                proposal.id,
                decision=ApprovalDecisionType.APPROVED,
                manager_identity="local_manager",
                expected_revision=proposal.revision,
                expected_payload_hash=proposal.payload_hash,
            )
            execution = AgentStateService.begin_execution(
                db,
                proposal.id,
                manager_identity="local_manager",
                tool_name="microsoft_graph.teams.send_chat_message",
            )
            write_job.state = AgentJobState.EXECUTING
            write_job.version += 1
            db.commit()

            recovered_write = AgentRecoveryService.recover(db, write_job.id)
            db.refresh(execution)
            assert recovered_write.state == AgentJobState.FAILED
            assert recovered_write.safe_error_code == "reconciliation_required"
            assert execution.state == ToolExecutionState.UNCERTAIN
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                db.execute(delete(AgentThread).where(AgentThread.id == thread_id))
                db.commit()


def test_concurrent_approval_attempts_resolve_to_one_decision() -> None:
    thread_id = None
    try:
        with SessionLocal() as db:
            thread = AgentStateService.create_thread(db, title="Concurrent approval")
            thread_id = thread.id
            job = AgentStateService.create_job(db, thread_id=thread.id, goal="Approve once")
            proposal = AgentStateService.create_proposal(
                db,
                job_id=job.id,
                action="teams.send_chat_message",
                destination={"chat_id": "chat-concurrent"},
                body="One approved body",
                reason="Concurrency test",
            )
            proposal_id = proposal.id
            payload_hash = proposal.payload_hash

        def approve_once():
            with SessionLocal() as concurrent_db:
                return AgentStateService.decide_proposal(
                    concurrent_db,
                    proposal_id,
                    decision=ApprovalDecisionType.APPROVED,
                    manager_identity="local_manager",
                    expected_revision=1,
                    expected_payload_hash=payload_hash,
                ).id

        with ThreadPoolExecutor(max_workers=2) as executor:
            decision_ids = list(executor.map(lambda _index: approve_once(), range(2)))

        assert decision_ids[0] == decision_ids[1]
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(func.count(ApprovalDecision.id)).where(
                        ApprovalDecision.proposal_id == proposal_id
                    )
                )
                == 1
            )
    finally:
        if thread_id is not None:
            with SessionLocal() as db:
                db.execute(delete(AgentThread).where(AgentThread.id == thread_id))
                db.commit()
