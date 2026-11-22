from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.db.session import SessionLocal
from app.models.enums import PrismLifecycleState
from app.models.prisms.prism_v22 import Prism
from app.schemas.prisms.prism_v22 import (
    PrismAgreementConfirm,
    PrismCreate,
    PrismOnboardingAnswerInput,
)
from app.services.errors import ConflictError
from app.services.prisms.prism_agreement_service import PrismAgreementService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.prisms.prism_onboarding_service import PrismOnboardingService


def test_onboarding_is_resumable_revisioned_and_moves_to_agreement_review() -> None:
    prism_id: uuid.UUID | None = None
    marker = uuid.uuid4().hex[:8]
    try:
        with SessionLocal() as db:
            prism = PrismLifecycleService.create(
                db,
                PrismCreate(
                    name=f"QA Release {marker}",
                    description="Watch release testing and blocked verification work.",
                ),
            )
            prism_id = prism.id
            session = PrismOnboardingService.start(db, prism.id)
            assert session["revision"] == 1
            assert session["status"] == "in_progress"
            assert len(session["questions"]) == 7
            assert PrismOnboardingService.start(db, prism.id)["id"] == session["id"]

            mission = session["questions"][0]
            session = PrismOnboardingService.answer(
                db,
                prism.id,
                mission.id,
                PrismOnboardingAnswerInput(
                    expected_revision=1,
                    custom_text="Keep releases safe and make blocked testing visible.",
                ),
            )
            assert session["revision"] == 2
            with pytest.raises(ConflictError):
                PrismOnboardingService.answer(
                    db,
                    prism.id,
                    session["questions"][1].id,
                    PrismOnboardingAnswerInput(expected_revision=1, selected_values=["blocker"]),
                )
            db.rollback()

            for question in session["questions"][1:]:
                if question.required:
                    value = question.choices[0]["value"]
                    session = PrismOnboardingService.answer(
                        db,
                        prism.id,
                        question.id,
                        PrismOnboardingAnswerInput(
                            expected_revision=session["revision"], selected_values=[value]
                        ),
                    )
                else:
                    session = PrismOnboardingService.answer(
                        db,
                        prism.id,
                        question.id,
                        PrismOnboardingAnswerInput(
                            expected_revision=session["revision"], skipped=True
                        ),
                    )
            assert session["status"] == "completed"
            assert session["current_question_id"] is None
            assert (
                PrismLifecycleService.get(db, prism.id).state
                == PrismLifecycleState.AWAITING_CONFIRMATION
            )
    finally:
        if prism_id is not None:
            with SessionLocal() as db:
                db.execute(delete(Prism).where(Prism.id == prism_id))
                db.commit()


def test_working_agreement_is_immutable_and_requires_explicit_confirmation() -> None:
    prism_id: uuid.UUID | None = None
    marker = uuid.uuid4().hex[:8]
    try:
        with SessionLocal() as db:
            prism = PrismLifecycleService.create(
                db,
                PrismCreate(
                    name=f"Executive Assistant {marker}",
                    description="Brief me on important Teams work in a friendly tone.",
                    template_key="executive_assistant",
                    template_version="1",
                ),
            )
            prism_id = prism.id
            session = PrismOnboardingService.start(db, prism.id)
            for question in session["questions"]:
                if not question.required:
                    payload = PrismOnboardingAnswerInput(
                        expected_revision=session["revision"], skipped=True
                    )
                elif question.question_type == "long_text":
                    payload = PrismOnboardingAnswerInput(
                        expected_revision=session["revision"],
                        custom_text="Keep me informed about important work.",
                    )
                else:
                    payload = PrismOnboardingAnswerInput(
                        expected_revision=session["revision"],
                        selected_values=[question.choices[0]["value"]],
                    )
                session = PrismOnboardingService.answer(db, prism.id, question.id, payload)

            agreement = PrismAgreementService.get_or_create(db, prism.id)
            assert agreement.status == "draft"
            assert agreement.revision == 1
            assert agreement.agreement["mission"] == "Keep me informed about important work."
            assert agreement.agreement["safety_rule"].endswith("explicit approval.")
            assert PrismAgreementService.get_or_create(db, prism.id).id == agreement.id

            confirmed, active_prism = PrismAgreementService.confirm(
                db,
                prism.id,
                PrismAgreementConfirm(
                    expected_agreement_revision=agreement.revision,
                    expected_lifecycle_version=PrismLifecycleService.get(
                        db, prism.id
                    ).lifecycle_version,
                ),
            )
            assert confirmed.status == "confirmed"
            assert confirmed.confirmed_at is not None
            assert active_prism.state == PrismLifecycleState.ACTIVE
    finally:
        if prism_id is not None:
            with SessionLocal() as db:
                db.execute(delete(Prism).where(Prism.id == prism_id))
                db.commit()
