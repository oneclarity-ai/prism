from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import ActionProposalState, PrismLifecycleState
from app.models.prisms.agent_v21 import ActionProposal, AgentJob, AgentThread
from app.models.prisms.prism_v22 import (
    Prism,
    PrismExternalEvent,
    PrismObservation,
    PrismObservationDraft,
)
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prisms.prism_conversation_service import PrismConversationService
from app.services.prisms.prism_draft_service import PrismDraftService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService


def _activate(db, name: str) -> Prism:
    prism = PrismLifecycleService.create(db, PrismCreate(name=name, description="Watches things."))
    for target, event, confirmed in (
        (PrismLifecycleState.ONBOARDING, "onboarding_started", False),
        (PrismLifecycleState.AWAITING_CONFIRMATION, "agreement_prepared", False),
        (PrismLifecycleState.ACTIVE, "agreement_confirmed", True),
    ):
        prism = PrismLifecycleService.transition(
            db,
            prism.id,
            target=target,
            expected_lifecycle_version=prism.lifecycle_version,
            event_type=event,
            agreement_confirmed=confirmed,
        )
    return prism


def _draft(db, prism: Prism, thread: AgentThread, event: PrismExternalEvent, state="pending"):
    now = datetime.now(timezone.utc)
    observation = PrismObservation(
        prism_id=prism.id,
        state="open",
        signal_type="production_incident",
        urgency="high",
        confidence=0.9,
        summary="Prod is down.",
        verified_facts=[],
        why_it_matters="Impact.",
        suggested_next_step="Follow up.",
        unknowns=[],
        evidence_event_ids=[str(event.id)],
        source_external_id=event.source_external_id,
        source_label="Engineering",
        fingerprint=uuid.uuid4().hex,
        first_seen_at=now,
        last_seen_at=now,
    )
    job = AgentJob(thread_id=thread.id, goal="Draft a follow-up")
    db.add_all([observation, job])
    db.flush()
    proposal = ActionProposal(
        job_id=job.id,
        logical_action_id=uuid.uuid4(),
        revision=1,
        action="teams.send_message",
        state=ActionProposalState(state),
        destination={"external_id": event.source_external_id},
        body="Hi, status?",
        reason="Follow up",
        evidence_ids=[],
        payload_hash="sha256:" + "0" * 64,
    )
    link = PrismObservationDraft(
        prism_id=prism.id,
        observation_id=observation.id,
        job_id=job.id,
        request_id=uuid.uuid4(),
        agreement_revision=prism.agreement_revision,
        destination_external_id=event.source_external_id,
        evidence_event_ids=[str(event.id)],
        created_at=now,
    )
    db.add_all([proposal, link])
    db.commit()
    return observation, proposal, link


def test_observation_drafts_expire_when_their_basis_changes() -> None:
    marker = uuid.uuid4().hex[:8]
    prism_id: uuid.UUID | None = None
    try:
        with SessionLocal() as db:
            prism = _activate(db, f"Drafts {marker}")
            prism_id = prism.id
            _, thread = PrismConversationService.canonical_thread(db, prism.id)
            event = PrismExternalEvent(
                prism_id=prism.id,
                tenant_id="t",
                microsoft_user_id="u",
                source_external_id=f"chat-{marker}",
                external_message_id="m1",
                event_kind="created",
                source_version="1",
                dedupe_key=uuid.uuid4().hex,
                occurred_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                sender_display_name="Asha",
                body_text="Prod is down",
                event_metadata={},
            )
            db.add(event)
            db.commit()

            # A current draft is left alone, and a v2.1 manual draft is never touched.
            observation, proposal, link = _draft(db, prism, thread, event)
            assert PrismDraftService.invalidate_if_stale(db, proposal.id) is False
            assert db.get(ActionProposal, proposal.id).state == ActionProposalState.PENDING

            # Evidence edited after the draft was prepared.
            db.add(
                PrismExternalEvent(
                    prism_id=prism.id,
                    tenant_id="t",
                    microsoft_user_id="u",
                    source_external_id=event.source_external_id,
                    external_message_id="m1",
                    event_kind="updated",
                    source_version="2",
                    dedupe_key=uuid.uuid4().hex,
                    occurred_at=datetime.now(timezone.utc),
                    sender_display_name="Asha",
                    body_text="Prod is fine",
                    event_metadata={},
                )
            )
            db.commit()
            assert PrismDraftService.invalidate_if_stale(db, proposal.id) is True
            db.expire_all()
            assert db.get(ActionProposal, proposal.id).state == ActionProposalState.EXPIRED
            assert db.get(PrismObservationDraft, link.id).invalidated_reason == "evidence_changed"

            # Agreement revision change expires an independent second draft.
            event2 = PrismExternalEvent(
                prism_id=prism.id,
                tenant_id="t",
                microsoft_user_id="u",
                source_external_id=f"chat2-{marker}",
                external_message_id="m2",
                event_kind="created",
                source_version="1",
                dedupe_key=uuid.uuid4().hex,
                occurred_at=datetime.now(timezone.utc),
                sender_display_name="Asha",
                body_text="Prod is down",
                event_metadata={},
            )
            db.add(event2)
            db.commit()
            _, second, _ = _draft(db, prism, thread, event2)
            db.get(Prism, prism.id).agreement_revision += 1
            db.commit()
            assert PrismDraftService.invalidate_for_prism(db, prism.id) == 1
            assert db.get(ActionProposal, second.id).state == ActionProposalState.EXPIRED

            # Resolved observation and archived Prism also expire; new drafts are refused.
            third_obs, third, _ = _draft(db, prism, thread, event2)
            third_obs.state = "resolved"
            db.commit()
            assert PrismDraftService.invalidate_if_stale(db, third.id) is True
            with pytest.raises(RuleViolationError):
                PrismDraftService.create(
                    db, prism.id, third_obs.id, request_id=uuid.uuid4(), instruction=None
                )
            with pytest.raises(NotFoundError):
                PrismDraftService.create(
                    db, prism.id, uuid.uuid4(), request_id=uuid.uuid4(), instruction=None
                )
    finally:
        with SessionLocal() as db:
            if prism_id:
                db.execute(delete(AgentThread).where(AgentThread.prism_id == prism_id))
                db.execute(delete(Prism).where(Prism.id == prism_id))
                db.commit()
