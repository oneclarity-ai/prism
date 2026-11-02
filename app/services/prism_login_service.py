from __future__ import annotations

import json
import logging
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prism_v22 import Prism
from app.models.work import PrismLogin
from app.services.errors import NotFoundError, RuleViolationError
from app.services.prism_agent_service import PrismAgentService
from app.services.qa_swarm_client import QaSwarmClient

logger = logging.getLogger(__name__)


def site_origin(site: str) -> str:
    parts = urlsplit(site if "://" in site else f"https://{site}")
    if not parts.netloc:
        raise RuleViolationError("That site address isn't valid")
    return f"{parts.scheme}://{parts.netloc}".lower()


def mask(username: str) -> str:
    """Enough to recognise the account in a list, never enough to use it."""

    name = username.strip()
    if "@" in name:
        local, _, domain = name.partition("@")
        return f"{local[:1]}***@{domain}"
    return f"{name[:1]}***{name[-1:]}" if len(name) > 2 else "***"


class PrismLoginService:
    """Logins a manager gave a Prism. The password only ever exists in the engine, encrypted."""

    @staticmethod
    def _scope(prism: Prism) -> str:
        return f"prism:{PrismAgentService.computer_key(prism.id)}"

    @classmethod
    def store(
        cls,
        db: Session,
        prism: Prism,
        client: QaSwarmClient,
        *,
        site: str,
        username: str,
        password: str,
        remember: bool,
    ) -> str:
        key = PrismAgentService.computer_key(prism.id)
        origin = site_origin(site)
        name = f"login:{key}:{origin}"
        for old in client.secrets(cls._scope(prism)):
            if old.get("name") == name:
                client.delete_secret(old["id"])
        secret_id = client.create_secret(
            name=name,
            scope=cls._scope(prism),
            value=json.dumps({"username": username, "password": password}),
        )
        row = db.scalar(
            select(PrismLogin).where(PrismLogin.prism_id == prism.id, PrismLogin.origin == origin)
        )
        if row is None:
            row = PrismLogin(prism_id=prism.id, origin=origin, username_masked="")
            db.add(row)
        row.username_masked = mask(username)
        row.swarm_secret_id = secret_id
        row.remember = remember
        db.flush()
        return origin

    @staticmethod
    def list(db: Session, prism_id: uuid.UUID) -> list[dict]:
        rows = db.scalars(
            select(PrismLogin).where(PrismLogin.prism_id == prism_id).order_by(PrismLogin.origin)
        )
        return [
            {
                "id": str(r.id),
                "site": r.origin,
                "username": r.username_masked,
                "remember": r.remember,
            }
            for r in rows
        ]

    @classmethod
    def remove(cls, db: Session, prism: Prism, login_id: uuid.UUID, client: QaSwarmClient) -> None:
        row = db.get(PrismLogin, login_id)
        if row is None or row.prism_id != prism.id:
            raise NotFoundError("That login was not found")
        if row.swarm_secret_id:
            client.delete_secret(row.swarm_secret_id)
        db.delete(row)
        db.flush()

    @classmethod
    def forget_once(cls, db: Session, prism: Prism | None, client: QaSwarmClient) -> None:
        """Logins given for one task only are removed when the task ends."""

        if prism is None:
            return
        for row in db.scalars(
            select(PrismLogin).where(
                PrismLogin.prism_id == prism.id, PrismLogin.remember.is_(False)
            )
        ):
            try:
                if row.swarm_secret_id:
                    client.delete_secret(row.swarm_secret_id)
            except Exception:  # noqa: BLE001 - an orphaned secret is replaced on the next login
                logger.warning("login_cleanup_failed", exc_info=False)
            db.delete(row)
        db.flush()

    @classmethod
    def forget_all(cls, db: Session, prism: Prism, client: QaSwarmClient) -> None:
        for old in client.secrets(cls._scope(prism)):
            client.delete_secret(old["id"])
        for row in db.scalars(select(PrismLogin).where(PrismLogin.prism_id == prism.id)):
            db.delete(row)
        db.flush()
