from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.prism_v22 import Prism
from app.models.work import PrismComputer
from app.services.brain_service import BrainService
from app.services.prism_presets import grants_for
from app.services.qa_swarm_client import QaSwarmClient

logger = logging.getLogger(__name__)

BASE_RULES = (
    "Work only on what the manager asked for. Be honest about what you could not do. "
    "Never invent results or sources."
)


class PrismAgentService:
    """Keeps one engine agent per Prism: its instructions and tools follow the Prism's role."""

    @staticmethod
    def computer_key(prism_id: uuid.UUID) -> str:
        return f"prism-{prism_id.hex[:8]}"

    @classmethod
    def instructions(cls, db: Session, prism: Prism) -> str:
        from app.services.prism_conversation_service import PrismConversationService
        from app.services.qa_plan_service import QaPlanService

        parts = [
            f"You are {prism.name}, a member of the manager's team. Your job: {prism.description}",
            BASE_RULES,
        ]
        if "qa_kit" in (prism.capabilities or []):
            parts.append(
                "You are a QA tester. You test web apps in a real browser and report bugs with evidence."
            )
        if prism.role_instructions:
            parts.append("How you work:\n" + prism.role_instructions)
        brain = BrainService.context(db)
        if brain:
            parts.append("What the whole team knows (shared memory):\n" + brain)
        try:
            _, thread = PrismConversationService.canonical_thread(db, prism.id)
            rules, _may_file = QaPlanService.house_rules(db, prism.id, thread.id)
        except Exception:  # noqa: BLE001 - rules are a bonus; the agent still works without them
            rules = []
        if rules:
            parts.append("House rules from the manager:\n" + "\n".join(f"- {r}" for r in rules))
        return "\n\n".join(parts)

    @classmethod
    def spec(cls, db: Session, prism: Prism) -> dict:
        settings = get_settings()
        return {
            "name": f"Prism: {prism.name}"[:200],
            "role": "prism",
            "description": prism.description[:1000],
            "instructions": cls.instructions(db, prism),
            "runtime": "openai_agents",
            "tool_grants": grants_for(prism.capabilities or ["browser"], prism.logins_policy),
            "max_turns": settings.work_max_turns_cap,
            "run_budget_usd": settings.work_budget_cap_usd,
        }

    @classmethod
    def computer_row(cls, db: Session, prism: Prism) -> PrismComputer:
        row = db.scalar(select(PrismComputer).where(PrismComputer.prism_id == prism.id))
        if row is None:
            row = PrismComputer(prism_id=prism.id, computer_key=cls.computer_key(prism.id))
            db.add(row)
            db.flush()
        return row

    @classmethod
    def ensure(cls, db: Session, prism: Prism, client: QaSwarmClient) -> str:
        """The engine agent id, created or updated only when the role changed since last time."""

        spec = cls.spec(db, prism)
        digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        row = cls.computer_row(db, prism)
        if row.swarm_agent_id and row.agent_hash == digest:
            return row.swarm_agent_id
        key = row.computer_key
        existing = client.find_agent(key)
        if existing is None:
            created = client.create_agent({"key": key, **spec})
            row.swarm_agent_id = created["id"]
        else:
            client.update_agent(existing["id"], spec)
            row.swarm_agent_id = existing["id"]
        row.agent_hash = digest
        row.synced_at = datetime.now(timezone.utc)
        db.commit()
        return row.swarm_agent_id
