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
from app.services.prism_presets import effective_grants
from app.services.prism_skill_service import SAFE_RULE, PrismSkillService
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
        manager_id = getattr(prism, "reports_to_prism_id", None)
        manager = db.get(Prism, manager_id) if manager_id else None
        parts.append(
            f"Your role is {getattr(prism, 'job_role', None) or 'Prism Specialist'} in {getattr(prism, 'department', None) or 'Operations'}. You report to {manager.name if manager else 'the user'}. Reporting lines do not grant permission to start other Prisms, read their private memory, or bypass action approvals."
        )
        if "qa_kit" in (prism.capabilities or []):
            parts.append(
                "You are a QA tester. You test web apps in a real browser and report bugs with evidence."
            )
        if prism.role_instructions:
            parts.append("How you work:\n" + prism.role_instructions)
        skills = PrismSkillService.context(db, prism.id)
        if skills:
            parts.append(SAFE_RULE + "\nEnabled skills:\n" + json.dumps(skills, ensure_ascii=False))
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
            "tool_grants": effective_grants(prism),
            "max_turns": min(
                prism.max_turns or settings.work_max_turns_cap, settings.work_max_turns_cap
            ),
            "run_budget_usd": min(
                float(prism.run_budget_usd or settings.work_budget_cap_usd),
                settings.work_budget_cap_usd,
            ),
            "monthly_budget_usd": float(prism.monthly_budget_usd or 100),
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
        existing = None
        if row.swarm_agent_id:
            # An adopted engine agent keeps its own id (and the tasks and runs attached to it).
            existing = next(
                (a for a in client.list_agents() if a.get("id") == row.swarm_agent_id), None
            )
        if existing is None:
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
