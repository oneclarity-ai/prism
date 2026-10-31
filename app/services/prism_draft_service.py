"""Teams drafts prepared from Prism observations.

Preparing a draft is safe: it reuses the v2.1 message -> review -> approval flow and
only creates a pending proposal. Nothing here approves or executes anything, and a
proposal whose Prism, agreement, or evidence changed is expired before it can be decided.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_v21 import ActionProposal, AgentJob
from app.models.enums import ActionProposalState, PrismLifecycleState
from app.models.prism_v22 import (
    Prism,
    PrismExternalEvent,
    PrismObservation,
    PrismObservationDraft,
)
from app.schemas.agent_v21 import AgentThreadMessageCreate
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prism_conversation_service import PrismConversationService

SIGNAL_LABELS = {
    "production_incident": "possible production incident",
    "missed_deadline": "deadline at risk",
    "blocker": "blocked work",
    "unanswered_message": "unanswered message",
    "customer_discussion": "customer discussion",
}
DEFAULT_INSTRUCTION = "Ask for the current status, who owns it, and the expected resolution time."
LIVE_STATES = (
    ActionProposalState.DRAFT,
    ActionProposalState.PENDING,
    ActionProposalState.APPROVED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrismDraftService:
    @staticmethod
    def _observation(
        db: Session, prism_id: uuid.UUID, observation_id: uuid.UUID
    ) -> PrismObservation:
        observation = db.get(PrismObservation, observation_id)
        if observation is None or observation.prism_id != prism_id:
            raise NotFoundError("Observation not found")
        return observation

    @classmethod
    def create(
        cls,
        db: Session,
        prism_id: uuid.UUID,
        observation_id: uuid.UUID,
        *,
        request_id: uuid.UUID,
        instruction: str | None,
    ) -> AgentJob:
        """Start a draft for the chat where the signal was seen; the user still approves it."""

        prism, thread = PrismConversationService.canonical_thread(db, prism_id)
        observation = cls._observation(db, prism_id, observation_id)
        existing = db.scalar(
            select(PrismObservationDraft).where(
                PrismObservationDraft.observation_id == observation.id,
                PrismObservationDraft.request_id == request_id,
            )
        )
        if existing is not None:
            return db.get(AgentJob, existing.job_id)
        if observation.state != "open":
            raise RuleViolationError(
                "This update is no longer open. Ask Prism directly if you still want a follow-up."
            )
        label = observation.source_label or "this Teams chat"
        # Only the user's words and a fixed signal label go into the request; Teams text is
        # untrusted and is read as evidence by the review, never copied into the instruction.
        content = (
            f"Draft a follow-up message to {label}. Context: Prism flagged a "
            f"{SIGNAL_LABELS.get(observation.signal_type, 'update')} in this chat. "
            f"{(instruction or DEFAULT_INSTRUCTION).strip()}"
        )[:4000]
        from app.api.routes.agent_v21 import create_manager_message

        job = create_manager_message(
            thread.id,
            AgentThreadMessageCreate(
                content=content, source_external_ids=[observation.source_external_id]
            ),
            db,
        )
        db.add(
            PrismObservationDraft(
                prism_id=prism.id,
                observation_id=observation.id,
                job_id=job.id,
                request_id=request_id,
                incident_id=observation.incident_id,
                agreement_revision=prism.agreement_revision,
                destination_external_id=observation.source_external_id,
                evidence_event_ids=list(observation.evidence_event_ids),
                created_at=_now(),
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return job

    @staticmethod
    def _stale_reason(
        db: Session,
        link: PrismObservationDraft,
        prism: Prism,
        observation: PrismObservation | None,
    ) -> str | None:
        if prism.state != PrismLifecycleState.ACTIVE:
            return "prism_inactive"
        if prism.agreement_revision != link.agreement_revision:
            return "agreement_changed"
        if observation is None or observation.state != "open":
            return "observation_closed"
        for event_id in link.evidence_event_ids:
            try:
                original = db.get(PrismExternalEvent, uuid.UUID(str(event_id)))
            except ValueError:
                continue
            if original is None:
                return "evidence_removed"
            changed = db.scalar(
                select(PrismExternalEvent.id)
                .where(
                    PrismExternalEvent.prism_id == link.prism_id,
                    PrismExternalEvent.source_external_id == original.source_external_id,
                    PrismExternalEvent.external_message_id == original.external_message_id,
                    PrismExternalEvent.event_kind.in_(("updated", "deleted")),
                    PrismExternalEvent.created_at > link.created_at,
                )
                .limit(1)
            )
            if changed is not None:
                return "evidence_changed"
        return None

    @classmethod
    def _expire(cls, db: Session, link: PrismObservationDraft, reason: str) -> int:
        proposals = list(
            db.scalars(
                select(ActionProposal)
                .where(ActionProposal.job_id == link.job_id, ActionProposal.state.in_(LIVE_STATES))
                .with_for_update()
            )
        )
        for proposal in proposals:
            proposal.state = ActionProposalState.EXPIRED
        if link.invalidated_at is None:
            link.invalidated_at = _now()
            link.invalidated_reason = reason
        return len(proposals)

    @classmethod
    def invalidate_if_stale(cls, db: Session, proposal_id: uuid.UUID) -> bool:
        """Expire a stale observation-derived proposal; return True when it was expired."""

        proposal = db.get(ActionProposal, proposal_id)
        if proposal is None:
            return False
        link = db.scalar(
            select(PrismObservationDraft).where(PrismObservationDraft.job_id == proposal.job_id)
        )
        if link is None:
            return False  # a v2.1 manual draft: unchanged behavior
        prism = db.get(Prism, link.prism_id)
        reason = cls._stale_reason(db, link, prism, db.get(PrismObservation, link.observation_id))
        if reason is None:
            return False
        expired = cls._expire(db, link, reason)
        db.commit()
        return bool(expired)

    @classmethod
    def invalidate_for_prism(cls, db: Session, prism_id: uuid.UUID) -> int:
        """Expire every stale live draft for a Prism (called when its conversation is opened)."""

        prism = db.get(Prism, prism_id)
        links = list(
            db.scalars(
                select(PrismObservationDraft).where(
                    PrismObservationDraft.prism_id == prism_id,
                    PrismObservationDraft.invalidated_at.is_(None),
                )
            )
        )
        total = 0
        for link in links:
            reason = cls._stale_reason(
                db, link, prism, db.get(PrismObservation, link.observation_id)
            )
            if reason is not None:
                total += cls._expire(db, link, reason)
        if links:
            db.commit()
        return total

    @staticmethod
    def list_for_observation(
        db: Session, prism_id: uuid.UUID, observation_id: uuid.UUID
    ) -> list[PrismObservationDraft]:
        PrismDraftService._observation(db, prism_id, observation_id)
        return list(
            db.scalars(
                select(PrismObservationDraft)
                .where(PrismObservationDraft.observation_id == observation_id)
                .order_by(PrismObservationDraft.created_at)
            )
        )
