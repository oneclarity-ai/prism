from __future__ import annotations

import logging
import unicodedata
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism, PrismLifecycleEvent
from app.schemas.prism_v22 import PrismCreate, PrismUpdate
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.prism_organization_service import PrismOrganizationService
from app.services.prism_presets import normalize_capabilities

logger = logging.getLogger(__name__)

LIFECYCLE_TRANSITIONS: dict[PrismLifecycleState, set[PrismLifecycleState]] = {
    PrismLifecycleState.DRAFT: {
        PrismLifecycleState.ONBOARDING,
        PrismLifecycleState.ARCHIVED,
    },
    PrismLifecycleState.ONBOARDING: {
        PrismLifecycleState.DRAFT,
        PrismLifecycleState.AWAITING_CONFIRMATION,
        PrismLifecycleState.ARCHIVED,
    },
    PrismLifecycleState.AWAITING_CONFIRMATION: {
        PrismLifecycleState.ONBOARDING,
        PrismLifecycleState.ACTIVE,
        PrismLifecycleState.ARCHIVED,
    },
    PrismLifecycleState.ACTIVE: {
        PrismLifecycleState.PAUSED,
        PrismLifecycleState.ARCHIVED,
    },
    PrismLifecycleState.PAUSED: {
        PrismLifecycleState.ACTIVE,
        PrismLifecycleState.ARCHIVED,
    },
    PrismLifecycleState.ARCHIVED: set(),
}


class PrismLifecycleService:
    """Owns v2.2 Prism identity and lifecycle; it never starts agent work."""

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()

    @classmethod
    def create(cls, db: Session, data: PrismCreate) -> Prism:
        PrismOrganizationService.lock(db)
        name = " ".join(data.name.split())
        normalized_name = cls.normalize_name(name)
        if not normalized_name:
            raise RuleViolationError("Prism name is required")
        description = data.description.strip()
        if not description:
            raise RuleViolationError("Prism description is required")
        if cls._active_name_exists(db, normalized_name):
            raise ConflictError("A non-archived Prism already uses this name")
        prism = Prism(
            id=uuid.uuid4(),
            name=name,
            normalized_name=normalized_name,
            description=description,
            template_key=data.template_key,
            template_version=data.template_version,
            color=data.color,
            capabilities=normalize_capabilities(data.template_key, data.capabilities),
            logins_policy=data.logins_policy,
            role_instructions=(data.role_instructions or "").strip() or None,
            state=PrismLifecycleState.ACTIVE if data.activate else PrismLifecycleState.DRAFT,
            lifecycle_version=1,
        )
        PrismOrganizationService.assign(db, prism, data, creating=True)
        db.add(prism)
        db.flush()
        db.add(
            PrismLifecycleEvent(
                prism_id=prism.id,
                sequence=1,
                # Onboarded in one step (job description, instructions, tools): ready to chat and work.
                event_type="created_active" if data.activate else "created",
                target_state=prism.state,
            )
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A non-archived Prism already uses this name") from exc
        db.refresh(prism)
        return prism

    @staticmethod
    def list_prisms(db: Session, *, include_archived: bool = False) -> list[Prism]:
        statement = select(Prism).order_by(Prism.updated_at.desc(), Prism.id.desc())
        if not include_archived:
            statement = statement.where(Prism.state != PrismLifecycleState.ARCHIVED)
        prisms = list(db.scalars(statement))
        # Most recently talked-to first; Prisms with no conversation fall back to updated_at.
        latest = {
            row.prism_id: row
            for row in db.execute(
                select(
                    AgentThread.prism_id,
                    AgentThreadMessage.created_at,
                    AgentThreadMessage.role,
                    AgentThreadMessage.content,
                )
                .join(AgentThreadMessage, AgentThreadMessage.thread_id == AgentThread.id)
                .where(AgentThread.prism_id.in_([prism.id for prism in prisms]))
                .distinct(AgentThread.prism_id)
                .order_by(AgentThread.prism_id, AgentThreadMessage.created_at.desc())
            )
        }
        for prism in prisms:
            row = latest.get(prism.id)
            prism.last_message_at = row.created_at if row else None
            prism.last_message_role = row.role if row else None
            prism.last_message_preview = " ".join(row.content.split())[:160] if row else None
        prisms.sort(key=lambda prism: prism.last_message_at or prism.updated_at, reverse=True)
        return prisms

    @staticmethod
    def get(db: Session, prism_id: uuid.UUID, *, include_archived: bool = True) -> Prism:
        prism = db.get(Prism, prism_id)
        if prism is None or (not include_archived and prism.state == PrismLifecycleState.ARCHIVED):
            raise NotFoundError("Prism was not found")
        return prism

    @classmethod
    def delete_archived(cls, db: Session, prism_id: uuid.UUID) -> None:
        """Permanently remove an archived Prism, its chats and its computer's saved logins."""

        prism = cls._locked_prism(db, prism_id)
        if prism.state != PrismLifecycleState.ARCHIVED:
            raise RuleViolationError("Archive a Prism before deleting it")
        cls._forget_computer(db, prism)
        db.execute(delete(AgentThread).where(AgentThread.prism_id == prism.id))
        db.delete(prism)
        db.commit()

    @staticmethod
    def _forget_computer(db: Session, prism: Prism) -> None:
        """Best effort: saved logins and the browser are cleared if the engine is reachable."""

        from app.services import qa_run_service
        from app.services.prism_agent_service import PrismAgentService
        from app.services.prism_login_service import PrismLoginService

        try:
            with qa_run_service.make_client() as client:
                PrismLoginService.forget_all(db, prism, client)
                client.reset_computer(PrismAgentService.computer_key(prism.id))
        except Exception:  # noqa: BLE001 - a Prism with no computer, or an engine that is down, can still go
            db.rollback()
            logger.info("prism_delete_computer_cleanup_skipped", exc_info=False)

    @classmethod
    def update(cls, db: Session, prism_id: uuid.UUID, data: PrismUpdate) -> Prism:
        PrismOrganizationService.lock(db)
        prism = cls._locked_prism(db, prism_id)
        if prism.lifecycle_version != data.expected_lifecycle_version:
            raise ConflictError("Prism changed; refresh before saving")
        if prism.state == PrismLifecycleState.ARCHIVED:
            raise RuleViolationError("Archived Prisms cannot be changed")
        if data.name is not None:
            name = " ".join(data.name.split())
            normalized_name = cls.normalize_name(name)
            if not normalized_name:
                raise RuleViolationError("Prism name is required")
            if normalized_name != prism.normalized_name and cls._active_name_exists(
                db, normalized_name, excluding=prism.id
            ):
                raise ConflictError("A non-archived Prism already uses this name")
            prism.name = name
            prism.normalized_name = normalized_name
        if data.description is not None:
            description = data.description.strip()
            if not description:
                raise RuleViolationError("Prism description is required")
            prism.description = description
        if data.color is not None:
            prism.color = data.color
        PrismOrganizationService.assign(db, prism, data)
        prism.lifecycle_version += 1
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A non-archived Prism already uses this name") from exc
        db.refresh(prism)
        return prism

    @classmethod
    def transition(
        cls,
        db: Session,
        prism_id: uuid.UUID,
        *,
        target: PrismLifecycleState,
        expected_lifecycle_version: int,
        event_type: str,
        reason: str | None = None,
        agreement_confirmed: bool = False,
    ) -> Prism:
        if target == PrismLifecycleState.ARCHIVED:
            PrismOrganizationService.lock(db)
        prism = cls._locked_prism(db, prism_id)
        if prism.lifecycle_version != expected_lifecycle_version:
            raise ConflictError("Prism changed; refresh before trying again")
        if prism.state == target:
            return prism
        if target not in LIFECYCLE_TRANSITIONS[prism.state]:
            raise RuleViolationError(
                f"Illegal Prism lifecycle transition: {prism.state} -> {target}"
            )
        if target == PrismLifecycleState.ACTIVE and not agreement_confirmed:
            raise RuleViolationError("A confirmed working agreement is required before activation")
        previous_state = prism.state
        if target == PrismLifecycleState.ARCHIVED:
            PrismOrganizationService.before_archive(db, prism)
        prism.state = target
        prism.lifecycle_version += 1
        db.add(
            PrismLifecycleEvent(
                prism_id=prism.id,
                sequence=(
                    int(
                        db.scalar(
                            select(func.max(PrismLifecycleEvent.sequence)).where(
                                PrismLifecycleEvent.prism_id == prism.id
                            )
                        )
                        or 0
                    )
                    + 1
                ),
                event_type=event_type,
                previous_state=previous_state,
                target_state=target,
                reason=reason.strip() if reason else None,
            )
        )
        db.commit()
        db.refresh(prism)
        return prism

    @staticmethod
    def events(db: Session, prism_id: uuid.UUID) -> list[PrismLifecycleEvent]:
        PrismLifecycleService.get(db, prism_id)
        return list(
            db.scalars(
                select(PrismLifecycleEvent)
                .where(PrismLifecycleEvent.prism_id == prism_id)
                .order_by(PrismLifecycleEvent.sequence)
            )
        )

    @staticmethod
    def _locked_prism(db: Session, prism_id: uuid.UUID) -> Prism:
        prism = db.scalar(select(Prism).where(Prism.id == prism_id).with_for_update())
        if prism is None:
            raise NotFoundError("Prism was not found")
        return prism

    @staticmethod
    def _active_name_exists(
        db: Session, normalized_name: str, *, excluding: uuid.UUID | None = None
    ) -> bool:
        statement = select(Prism.id).where(
            Prism.normalized_name == normalized_name,
            Prism.state != PrismLifecycleState.ARCHIVED,
        )
        if excluding is not None:
            statement = statement.where(Prism.id != excluding)
        return db.scalar(statement) is not None
