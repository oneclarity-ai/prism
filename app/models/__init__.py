"""Import all ORM models so SQLAlchemy metadata and Alembic can discover them."""

from app.models.agent_run import AgentRun
from app.models.agent_v21 import (
    ActionProposal,
    AgentActionPlan,
    AgentConversationReview,
    AgentFeedbackEvent,
    AgentJob,
    AgentJobSource,
    AgentPreference,
    AgentSourceMessage,
    AgentStep,
    AgentThread,
    AgentThreadAlias,
    AgentThreadMessage,
    ApprovalDecision,
    ToolExecution,
)
from app.models.automation_action import AutomationAction
from app.models.automation_run import AutomationRun
from app.models.blocker import Blocker
from app.models.brain import BrainEntry
from app.models.commitment import Commitment
from app.models.conversation import Conversation
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.employee_alias import EmployeeAlias
from app.models.escalation import Escalation
from app.models.escalation_decision import EscalationDecision
from app.models.intelligence import (
    DependencyEdge,
    ManagementDecision,
    ManagementRisk,
    ManagerFeedback,
)
from app.models.llm_usage import LLMUsage
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
from app.models.message import Message
from app.models.microsoft_connection import MicrosoftConnection
from app.models.microsoft_oauth_state import MicrosoftOAuthState
from app.models.microsoft_subscription import MicrosoftTeamsSubscription
from app.models.prism_v22 import (
    Prism,
    PrismBudget,
    PrismExternalEvent,
    PrismIncident,
    PrismIncidentEvent,
    PrismLifecycleEvent,
    PrismNotification,
    PrismNotificationSetting,
    PrismObservation,
    PrismObservationDraft,
    PrismObservationFeedback,
    PrismOnboardingAnswer,
    PrismOnboardingQuestion,
    PrismOnboardingSession,
    PrismPerson,
    PrismPresence,
    PrismRun,
    PrismSignalPreference,
    PrismTeamsSourceCursor,
    PrismTeamsSourcePolicy,
    PrismTeamsSourceRule,
    PrismTriggerPolicy,
    PrismWorkingAgreement,
)
from app.models.project import Project
from app.models.provider_credential import ProviderCredential
from app.models.qa import QaApproval, QaRun
from app.models.response_state import BlockerDependency, ConversationQuestion, ConversationState
from app.models.task import Task
from app.models.work import PrismComputer, PrismLogin

__all__ = [
    "BrainEntry",
    "QaApproval",
    "QaRun",
    "PrismComputer",
    "PrismLogin",
    "Blocker",
    "AgentRun",
    "AgentThread",
    "AgentThreadAlias",
    "AgentThreadMessage",
    "AgentJob",
    "AgentJobSource",
    "AgentActionPlan",
    "AgentSourceMessage",
    "AgentStep",
    "ActionProposal",
    "AgentConversationReview",
    "AgentPreference",
    "AgentFeedbackEvent",
    "ApprovalDecision",
    "ToolExecution",
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
    "ProviderCredential",
    "Prism",
    "PrismExternalEvent",
    "PrismLifecycleEvent",
    "PrismOnboardingSession",
    "PrismOnboardingQuestion",
    "PrismOnboardingAnswer",
    "PrismObservation",
    "PrismObservationDraft",
    "PrismObservationFeedback",
    "PrismSignalPreference",
    "PrismBudget",
    "PrismIncident",
    "PrismIncidentEvent",
    "PrismNotification",
    "PrismNotificationSetting",
    "PrismPresence",
    "PrismPerson",
    "PrismWorkingAgreement",
    "PrismTeamsSourcePolicy",
    "PrismTeamsSourceRule",
    "PrismTeamsSourceCursor",
    "PrismTriggerPolicy",
    "PrismRun",
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
