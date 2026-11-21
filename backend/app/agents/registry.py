"""Catalog of agent roles. Add a role: create app/agents/<role>/ with definition.py + SKILL.md, then list it here."""

from app.agents.base import AgentDefinition
from app.agents.marketing.definition import DEFINITION as MARKETING
from app.agents.qa.definition import DEFINITION as QA
from app.agents.sales.definition import DEFINITION as SALES
from app.agents.support.definition import DEFINITION as SUPPORT

CATALOG: list[AgentDefinition] = [QA, SALES, MARKETING, SUPPORT]


def available() -> list[AgentDefinition]:
    return [d for d in CATALOG if d.status == "available"]


def by_key(key: str) -> AgentDefinition | None:
    return next((d for d in CATALOG if d.key == key), None)
