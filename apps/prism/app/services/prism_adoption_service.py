from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism
from app.models.work import PrismComputer
from app.schemas.prism_v22 import PrismCreate
from app.services.errors import ConflictError, RuleViolationError
from app.services.prism_agent_service import PrismAgentService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.qa_swarm_client import QaSwarmClient

logger = logging.getLogger(__name__)

_NAME_PREFIX = "Prism:"


class PrismAdoptionService:
    """Turns engine-only agents into Prisms, so a Prism is the only kind of agent there is.

    The engine agent keeps its id (its tasks and runs stay attached). Its description, playbook,
    tool grants and limits are copied into the Prism, which is the source of truth from then on.
    """

    @staticmethod
    def _clean_name(raw: str) -> str:
        name = (raw or "").strip()
        if name.lower().startswith(_NAME_PREFIX.lower()):
            name = name[len(_NAME_PREFIX) :].strip()
        return name[:120]

    @classmethod
    def adopt_all(cls, db: Session, client: QaSwarmClient) -> list[Prism]:
        known_ids = {row for row in db.scalars(select(PrismComputer.swarm_agent_id)) if row}
        adopted: list[Prism] = []
        for agent in client.list_agents():
            key = str(agent.get("key") or "")
            if (
                not agent.get("id")
                or agent["id"] in known_ids
                or key.startswith("prism-")
                or agent.get("status") != "active"
            ):
                continue
            try:
                adopted.append(cls._adopt(db, agent))
            except (ConflictError, RuleViolationError):
                db.rollback()
                logger.info("prism_adoption_skipped key=%s", key)
        return adopted

    @classmethod
    def _adopt(cls, db: Session, agent: dict) -> Prism:
        name = cls._clean_name(str(agent.get("name") or agent.get("key") or "Prism"))
        description = (str(agent.get("description") or "").strip() or name)[:8000]
        prism = PrismLifecycleService.create(
            db, PrismCreate(name=name, description=description, activate=True)
        )
        prism.role_instructions = (str(agent.get("instructions") or "").strip()) or None
        grants = agent.get("tool_grants") or {}
        prism.tool_grants = {
            k: v for k, v in grants.items() if v in ("allowed", "ask_first", "off")
        } or None
        prism.max_turns = agent.get("max_turns") or None
        prism.run_budget_usd = agent.get("run_budget_usd") or None
        prism.monthly_budget_usd = agent.get("monthly_budget_usd") or None
        db.add(
            PrismComputer(
                prism_id=prism.id,
                computer_key=PrismAgentService.computer_key(prism.id),
                swarm_agent_id=str(agent["id"]),
            )
        )
        assert prism.state == PrismLifecycleState.ACTIVE
        db.commit()
        db.refresh(prism)
        return prism
