"""Import all ORM models so SQLAlchemy metadata and Alembic can discover them."""

from app.models.blocker import Blocker
from app.models.response_state import BlockerDependency, ConversationQuestion, ConversationState
from app.models.llm_usage import LLMUsage
from app.models.agent_run import AgentRun
from app.models.automation_action import AutomationAction
from app.models.commitment import Commitment
from app.models.conversation import Conversation
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.employee_alias import EmployeeAlias
from app.models.escalation import Escalation
from app.models.escalation_decision import EscalationDecision
from app.models.message import Message
from app.models.automation_run import AutomationRun
from app.models.microsoft_connection import MicrosoftConnection
from app.models.microsoft_oauth_state import MicrosoftOAuthState
from app.models.microsoft_subscription import MicrosoftTeamsSubscription
from app.models.management_context import ManagementContext
from app.models.memory import (
    ActivityEvent,
    ManagementProcedure,
    MemoryEpisode,
    MemoryEvidenceLink,
    MemoryFact,
    MemoryJob,
    MemoryRelation,
    MemorySource,
    MemorySummary,
)
from app.models.project import Project
from app.models.task import Task
from app.models.intelligence import DependencyEdge, ManagementDecision, ManagementRisk, ManagerFeedback

__all__ = [
    "Blocker",
    "AgentRun",
    "AutomationAction",
    "Commitment",
    "Conversation",
    "DailyUpdate",
    "Employee",
    "EmployeeAlias",
    "Escalation",
    "EscalationDecision",
    "Message",
    "AutomationRun",
    "MicrosoftConnection",
    "MicrosoftOAuthState",
    "MicrosoftTeamsSubscription",
    "ManagementContext",
    "ActivityEvent",
    "MemorySource",
    "MemoryFact",
    "MemoryEpisode",
    "MemoryRelation",
    "MemoryEvidenceLink",
    "MemorySummary",
    "ManagementProcedure",
    "MemoryJob",
    "Project",
    "Task",
    "BlockerDependency",
    "ConversationQuestion",
    "ConversationState",
    "LLMUsage",
    "DependencyEdge",
    "ManagementDecision",
    "ManagementRisk",
    "ManagerFeedback",
]
