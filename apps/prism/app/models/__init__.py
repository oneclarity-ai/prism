"""Import all ORM models so SQLAlchemy metadata and Alembic can discover them."""

from app.models.engine.work import PrismComputer, PrismLogin
from app.models.llm.llm_usage import LLMUsage
from app.models.llm.provider_credential import ProviderCredential
from app.models.management.automation_action import AutomationAction
from app.models.management.automation_run import AutomationRun
from app.models.management.blocker import Blocker
from app.models.management.commitment import Commitment
from app.models.management.conversation import Conversation
from app.models.management.daily_update import DailyUpdate
from app.models.management.escalation import Escalation
from app.models.management.escalation_decision import EscalationDecision
from app.models.management.intelligence import (
    DependencyEdge,
    ManagementDecision,
    ManagementRisk,
    ManagerFeedback,
)
from app.models.management.message import Message
from app.models.management.project import Project
from app.models.management.response_state import (
    BlockerDependency,
    ConversationQuestion,
    ConversationState,
)
from app.models.management.task import Task
from app.models.memory.brain import BrainEntry
from app.models.memory.management_context import ManagementContext
from app.models.memory.memory import (
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
from app.models.people.employee import Employee
from app.models.people.employee_alias import EmployeeAlias
from app.models.prisms.agent_run import AgentRun
from app.models.prisms.agent_v21 import (
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
from app.models.prisms.prism_skill import PrismSkill, PrismSkillAssignment, PrismSkillSetup
from app.models.prisms.prism_v22 import (
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
from app.models.qa.qa import QaApproval, QaRun
from app.models.teams.microsoft_connection import MicrosoftConnection
from app.models.teams.microsoft_oauth_state import MicrosoftOAuthState
from app.models.teams.microsoft_subscription import MicrosoftTeamsSubscription

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
    "PrismSkill",
    "PrismSkillAssignment",
    "PrismSkillSetup",
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
