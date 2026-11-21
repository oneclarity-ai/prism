from __future__ import annotations

import uuid
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prism_v22 import Prism
from app.models.qa import QA_ACTIVE_STATES, QaRun
from app.services import qa_run_service
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prism_agent_service import PrismAgentService
from app.services.prism_login_service import PrismLoginService
from app.services.qa_run_service import QaRunService
from app.services.qa_swarm_client import SwarmError


class ComputerService:
    """What a manager sees of a Prism's computer. Nothing here names the engine."""

    @staticmethod
    def _prism(db: Session, prism_id: uuid.UUID) -> Prism:
        prism = db.get(Prism, prism_id)
        if prism is None:
            raise NotFoundError("Prism was not found")
        return prism

    @classmethod
    def state(cls, db: Session, prism_id: uuid.UUID) -> dict:
        prism = cls._prism(db, prism_id)
        ok, reason = QaRunService.available()
        if not ok:
            return {"state": "unavailable", "reason": reason, "run_id": None}
        active = db.scalar(
            select(QaRun)
            .where(QaRun.prism_id == prism.id, QaRun.state.in_(QA_ACTIVE_STATES))
            .order_by(QaRun.created_at.desc())
        )
        if active is not None:
            state = {"starting": "starting", "waiting_approval": "waiting"}.get(
                active.state, "working"
            )
            return {"state": state, "reason": None, "run_id": str(active.id)}
        try:
            with qa_run_service.make_client() as client:
                client.status()
        except SwarmError:
            return {
                "state": "unavailable",
                "reason": "My computer is offline right now.",
                "run_id": None,
            }
        return {"state": "asleep", "reason": None, "run_id": None}

    @classmethod
    def live(cls, db: Session, prism_id: uuid.UUID) -> Iterator[bytes]:
        """The Prism's screen as it happens (multipart JPEG). Raises before the first byte if it is asleep."""
        prism = cls._prism(db, prism_id)
        client = qa_run_service.make_client()
        try:
            response = client.open_computer_stream(PrismAgentService.computer_key(prism.id))
        except SwarmError as exc:
            client.close()
            raise NotFoundError("My computer is asleep right now.") from exc

        def frames() -> Iterator[bytes]:
            try:
                yield from response.iter_raw()
            except Exception:  # the computer stopped or the viewer left; the stream just ends
                return
            finally:
                response.close()
                client.close()

        return frames()

    @classmethod
    def _require_idle(cls, db: Session, prism: Prism) -> None:
        busy = db.scalar(
            select(QaRun.id).where(QaRun.prism_id == prism.id, QaRun.state.in_(QA_ACTIVE_STATES))
        )
        if busy is not None:
            raise RuleViolationError("I'm in the middle of a task. Stop it first.")

    @classmethod
    def stop(cls, db: Session, prism_id: uuid.UUID) -> dict:
        prism = cls._prism(db, prism_id)
        cls._require_idle(db, prism)
        try:
            with qa_run_service.make_client() as client:
                client.stop_computer(PrismAgentService.computer_key(prism.id))
        except SwarmError as exc:
            raise RuleViolationError(str(exc)) from exc
        return cls.state(db, prism_id)

    @classmethod
    def reset(cls, db: Session, prism_id: uuid.UUID) -> dict:
        """Forget every login, cookie and download: the next task starts with a clean browser."""

        prism = cls._prism(db, prism_id)
        cls._require_idle(db, prism)
        try:
            with qa_run_service.make_client() as client:
                PrismLoginService.forget_all(db, prism, client)
                client.reset_computer(PrismAgentService.computer_key(prism.id))
        except SwarmError as exc:
            db.rollback()
            raise RuleViolationError(str(exc)) from exc
        db.commit()
        return cls.state(db, prism_id)
