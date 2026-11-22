"""What an agent role is, in code.

Each role lives in its own folder under app/agents/<role>/ with:
  definition.py  -> DEFINITION: AgentDefinition (identity, department, tools, budgets, status)
  SKILL.md       -> the role's instructions (copied into the agent row when it is created)

The database row (table `agents`) is the live, editable copy. The definition is the template.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    role: str
    department: str
    description: str
    folder: Path
    status: Literal["available", "planned"] = "available"
    runtime: str = "openai_agents"
    tool_grants: dict[str, str] = field(default_factory=dict)
    max_turns: int = 80
    run_budget_usd: Decimal = Decimal("3.00")
    monthly_budget_usd: Decimal = Decimal("100.00")

    @property
    def instructions(self) -> str:
        skill = self.folder / "SKILL.md"
        return skill.read_text() if skill.exists() else ""
