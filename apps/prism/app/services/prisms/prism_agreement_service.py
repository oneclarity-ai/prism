"""Build and confirm the explicit working agreement for a Prism."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.enums import PrismLifecycleState, PrismOnboardingStatus
from app.models.prisms.prism_v22 import (
    Prism,
    PrismOnboardingAnswer,
    PrismOnboardingSession,
    PrismWorkingAgreement,
)
from app.schemas.prisms.prism_v22 import PrismAgreementConfirm
from app.services.errors import ConflictError, RuleViolationError
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService


class PrismAgreementService:
    """Keeps agreement construction deterministic, display-safe, and revisioned."""

    GENERATOR_VERSION = "server-agreement-v1"

    @classmethod
    def get_or_create(cls, db: Session, prism_id: uuid.UUID) -> PrismWorkingAgreement:
        prism = PrismLifecycleService.get(db, prism_id)
        existing = db.scalar(
            select(PrismWorkingAgreement)
            .where(PrismWorkingAgreement.prism_id == prism_id)
            .order_by(PrismWorkingAgreement.revision.desc())
        )
        if existing is not None:
            return existing
        if prism.state not in {
            PrismLifecycleState.AWAITING_CONFIRMATION,
            PrismLifecycleState.ACTIVE,
        }:
            raise RuleViolationError(
                "Complete onboarding before reviewing this Prism's working agreement"
            )
        session = db.scalar(
            select(PrismOnboardingSession)
            .where(PrismOnboardingSession.prism_id == prism_id)
            .options(
                selectinload(PrismOnboardingSession.answers).selectinload(
                    PrismOnboardingAnswer.question
                ),
            )
        )
        if session is None or session.status != PrismOnboardingStatus.COMPLETED:
            raise RuleViolationError(
                "Complete onboarding before reviewing this Prism's working agreement"
            )
        prism = db.scalar(select(Prism).where(Prism.id == prism_id).with_for_update())
        assert prism is not None
        agreement = PrismWorkingAgreement(
            prism_id=prism.id,
            onboarding_session_id=session.id,
            revision=prism.agreement_revision + 1,
            status="draft",
            template_key=prism.template_key,
            template_version=prism.template_version,
            agreement=cls._build_content(prism, session),
            source_answer_ids=[str(answer.id) for answer in session.answers],
            generation_metadata={"generator": cls.GENERATOR_VERSION, "provider": "none"},
        )
        prism.agreement_revision = agreement.revision
        db.add(agreement)
        if agreement.agreement.get("work"):
            from app.services.prisms.prism_profile_service import PrismProfileService

            PrismProfileService.ensure_instructions(prism, agreement.agreement)
        db.commit()
        db.refresh(agreement)
        return agreement

    @classmethod
    def confirm(
        cls, db: Session, prism_id: uuid.UUID, data: PrismAgreementConfirm
    ) -> tuple[PrismWorkingAgreement, Prism]:
        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(
                PrismWorkingAgreement.prism_id == prism_id,
                PrismWorkingAgreement.revision == data.expected_agreement_revision,
            )
            .with_for_update()
        )
        if agreement is None:
            raise ConflictError("The working agreement changed; refresh before confirming")
        prism = db.scalar(select(Prism).where(Prism.id == prism_id).with_for_update())
        if prism is None:
            raise ConflictError("The Prism is no longer available")
        if prism.lifecycle_version != data.expected_lifecycle_version:
            raise ConflictError("Prism changed; refresh before confirming")
        if agreement.status == "confirmed" and prism.state == PrismLifecycleState.ACTIVE:
            return agreement, prism
        if agreement.status != "draft" or prism.state != PrismLifecycleState.AWAITING_CONFIRMATION:
            raise RuleViolationError("This Prism is not waiting for agreement confirmation")
        agreement.status = "confirmed"
        agreement.confirmed_at = datetime.now(UTC)
        db.flush()
        prism = PrismLifecycleService.transition(
            db,
            prism.id,
            target=PrismLifecycleState.ACTIVE,
            expected_lifecycle_version=data.expected_lifecycle_version,
            event_type="agreement_confirmed",
            agreement_confirmed=True,
        )
        db.refresh(agreement)
        return agreement, prism

    @staticmethod
    def _build_content(prism: Prism, session: PrismOnboardingSession) -> dict:
        by_key = {answer.question.key: answer for answer in session.answers}

        def answer_text(key: str, fallback: str = "Not specified") -> str:
            answer = by_key.get(key)
            if answer is None or answer.skipped:
                return fallback
            if answer.custom_text:
                return answer.custom_text
            labels = {choice["value"]: choice["label"] for choice in answer.question.choices}
            return (
                ", ".join(labels.get(value, value) for value in answer.selected_values) or fallback
            )

        def answer_list(key: str) -> list[str]:
            value = answer_text(key, "")
            return [part for part in value.split(", ") if part]

        answers = [
            {
                "key": a.question.key,
                "question": a.question.prompt,
                "answer": answer_text(a.question.key, ""),
            }
            for a in sorted(session.answers, key=lambda a: a.question.position)
            if not a.skipped and answer_text(a.question.key, "")
        ]
        return {
            "work": prism.template_key == "blank" and get_settings().prism_v24_enabled,
            "answers": answers,
            "mission": answer_text("mission", prism.description),
            "attention_signals": answer_list("urgent_signals"),
            "regular_brief": answer_text("regular_brief"),
            "teams_scope": answer_text("teams_scope"),
            "tone": answer_text("tone"),
            "allowed_proposals": answer_list("allowed_proposals"),
            "restrictions": answer_text("restrictions", "No additional restrictions specified."),
            "safety_rule": "Prism may only prepare recommendations or Teams drafts. Nothing is sent without your explicit approval.",
            "current_limitations": "Teams monitoring, schedules, and proactive updates are added in later phases.",
        }
