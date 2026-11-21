"""Adopt the v2.1 canonical conversation as an Executive Assistant Prism.

The original thread, jobs, evidence, plans, approvals, executions, and deep links stay
exactly where they are; only the thread gains an owner. The Prism starts Active with a
minimal confirmed agreement and *manual* monitoring, and no automatic run may start until
the user acknowledges the migration review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PrismLifecycleState, PrismOnboardingStatus
from app.models.prisms.agent_v21 import AgentPreference, AgentThread
from app.models.prisms.prism_v22 import PrismOnboardingSession, PrismWorkingAgreement
from app.schemas.prisms.prism_v22 import PrismCreate
from app.services.errors import RuleViolationError
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.prisms.prism_run_service import PrismRunService

logger = logging.getLogger(__name__)

MIGRATED_FLAG = "migrated_from_v21"
GENERATOR = "migrated-from-v2.1"
BASE_NAME = "Executive Assistant"


class PrismMigrationService:
    @staticmethod
    def legacy_thread(db: Session) -> AgentThread | None:
        return db.scalar(
            select(AgentThread).where(
                AgentThread.is_canonical.is_(True), AgentThread.prism_id.is_(None)
            )
        )

    @classmethod
    def _unused_name(cls, db: Session) -> str:
        name, attempt = BASE_NAME, 1
        while PrismLifecycleService._active_name_exists(
            db, PrismLifecycleService.normalize_name(name)
        ):
            attempt += 1
            name = f"{BASE_NAME} (v2.1 history{'' if attempt == 2 else f' {attempt - 1}'})"
        return name

    @classmethod
    def adopt_legacy_conversation(cls, db: Session) -> dict[str, str | None]:
        """Idempotent: with no un-owned legacy conversation there is nothing to do."""

        thread = cls.legacy_thread(db)
        if thread is None:
            return {"status": "nothing_to_migrate", "prism_id": None}
        preferences = list(
            db.scalars(
                select(AgentPreference).where(
                    AgentPreference.prism_id.is_(None), AgentPreference.is_active.is_(True)
                )
            )
        )
        carried = [item.instruction for item in preferences if item.scope == "general"]
        prism = PrismLifecycleService.create(
            db,
            PrismCreate(
                name=cls._unused_name(db),
                description=(
                    "Your original Prism conversation, migrated from v2.1. Review its working "
                    "agreement before turning on automatic monitoring."
                ),
                template_key="executive_assistant",
                template_version="v2.1-migration",
            ),
        )
        session = PrismOnboardingSession(
            prism_id=prism.id,
            status=PrismOnboardingStatus.COMPLETED,
            question_set_version=GENERATOR,
            generation_note="Migrated from the v2.1 conversation; no onboarding was needed.",
        )
        db.add(session)
        db.flush()
        agreement = PrismWorkingAgreement(
            prism_id=prism.id,
            onboarding_session_id=session.id,
            revision=1,
            status="confirmed",
            template_key=prism.template_key,
            template_version=prism.template_version,
            agreement={
                "mission": prism.description,
                "attention_signals": [],
                "regular_brief": "Not specified",
                "teams_scope": "All accessible Teams chats",
                "tone": "Carried over from your saved preferences.",
                "allowed_proposals": ["Teams drafts for your approval"],
                "restrictions": " ".join(carried) or "No additional restrictions specified.",
                "safety_rule": "Prism may only prepare recommendations or Teams drafts. Nothing is sent without your explicit approval.",
                "current_limitations": "Migrated minimal agreement. No proactive signals are enabled until you add them.",
            },
            source_answer_ids=[],
            generation_metadata={
                "generator": GENERATOR,
                "provider": "none",
                "review_required": True,
            },
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(agreement)
        prism.agreement_revision = 1
        db.commit()
        for target, event in (
            (PrismLifecycleState.ONBOARDING, "migrated_from_v21"),
            (PrismLifecycleState.AWAITING_CONFIRMATION, "migrated_from_v21"),
            (PrismLifecycleState.ACTIVE, "migrated_from_v21"),
        ):
            prism = PrismLifecycleService.transition(
                db,
                prism.id,
                target=target,
                expected_lifecycle_version=prism.lifecycle_version,
                event_type=event,
                reason="Adopted the v2.1 canonical conversation.",
                agreement_confirmed=target == PrismLifecycleState.ACTIVE,
            )
        thread.prism_id = prism.id
        thread.source_metadata = {
            **(thread.source_metadata or {}),
            MIGRATED_FLAG: True,
            "prism_context": {"prism_id": str(prism.id), "agreement_revision": 1},
        }
        # Legacy preferences stay for v2.1; each is copied so the Prism keeps its own.
        for item in preferences:
            db.add(
                AgentPreference(
                    prism_id=prism.id,
                    instruction=item.instruction,
                    scope=item.scope,
                    source_kind="migrated_v21",
                    source_thread_id=thread.id,
                    is_active=True,
                    expires_at=item.expires_at,
                )
            )
        db.commit()
        # Manual-only until the user chooses a schedule.
        PrismRunService.get_policy(db, prism.id)
        logger.info("prism_v21_conversation_adopted prism_id=%s thread_id=%s", prism.id, thread.id)
        return {"status": "migrated", "prism_id": str(prism.id)}

    @staticmethod
    def review_required(db: Session, prism_id) -> bool:
        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(
                PrismWorkingAgreement.prism_id == prism_id,
                PrismWorkingAgreement.status == "confirmed",
            )
            .order_by(PrismWorkingAgreement.revision.desc())
        )
        return bool(agreement and agreement.generation_metadata.get("review_required"))

    @staticmethod
    def acknowledge_review(db: Session, prism_id) -> None:
        agreement = db.scalar(
            select(PrismWorkingAgreement)
            .where(
                PrismWorkingAgreement.prism_id == prism_id,
                PrismWorkingAgreement.status == "confirmed",
            )
            .order_by(PrismWorkingAgreement.revision.desc())
            .with_for_update()
        )
        if agreement is None or not agreement.generation_metadata.get("review_required"):
            raise RuleViolationError("This Prism has no pending migration review")
        agreement.generation_metadata = {
            **agreement.generation_metadata,
            "review_required": False,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        db.commit()
