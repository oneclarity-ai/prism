from enum import Enum


class StringEnum(str, Enum):
    """String-backed enum suitable for PostgreSQL enum columns and API values."""


class ProjectStatus(StringEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(StringEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CommitmentStatus(StringEnum):
    OPEN = "open"
    COMPLETED = "completed"
    MISSED = "missed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class BlockerStatus(StringEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class BlockerSeverity(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(StringEnum):
    OPEN = "open"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class EscalationDecisionType(StringEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EscalationType(StringEnum):
    BLOCKER = "blocker"
    MISSED_COMMITMENT = "missed_commitment"
    PROJECT_RISK = "project_risk"
    ARCHITECTURE_CHANGE = "architecture_change"
    PROJECT_DEADLINE_CHANGE = "project_deadline_change"
    PRODUCTION_DEPLOYMENT = "production_deployment"
    APPROVAL_REQUIRED = "approval_required"
    UNCERTAINTY = "uncertainty"
    OTHER = "other"


class ConversationChannel(StringEnum):
    TEAMS = "teams"
    OUTLOOK = "outlook"
    GMAIL = "gmail"
    INTERNAL = "internal"


class ConversationType(StringEnum):
    DIRECT = "direct"
    GROUP = "group"
    MEETING = "meeting"


class MessageDirection(StringEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageDeliveryStatus(StringEnum):
    RECORDED = "recorded"
    DELIVERED = "delivered"
    FAILED = "failed"


class SenderType(StringEnum):
    EMPLOYEE = "employee"
    AGENT = "agent"
    MANAGER = "manager"
    SYSTEM = "system"


class AutomationStatus(StringEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class MicrosoftSubscriptionStatus(StringEnum):
    ACTIVE = "active"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"


class AgentRunStatus(StringEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AgentAnalysisType(StringEnum):
    BLOCKER = "blocker"
    UPDATE = "update"
    UNCLEAR = "unclear"


class AutomationActionType(StringEnum):
    DAILY_CHECKIN = "daily_checkin"
    NO_RESPONSE_FOLLOWUP = "no_response_followup"
    MISSED_COMMITMENT_FOLLOWUP = "missed_commitment_followup"
    DAILY_DIGEST = "daily_digest"
    ESCALATION_NOTIFICATION = "escalation_notification"
    BLOCKER_SOURCE_ACKNOWLEDGEMENT = "blocker_source_acknowledgement"
    BLOCKER_OWNER_REQUEST = "blocker_owner_request"
    BLOCKER_OWNER_CLARIFICATION = "blocker_owner_clarification"


class AutomationActionStatus(StringEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    SKIPPED = "skipped"
    FAILED = "failed"


class ActivityEventType(StringEnum):
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    DAILY_UPDATE_RECEIVED = "daily_update_received"
    DAILY_UPDATE_CREATED = "daily_update_created"
    DAILY_UPDATE_CHANGED = "daily_update_changed"
    BLOCKER_CREATED = "blocker_created"
    BLOCKER_DEPENDENCY_OWNER_CHANGED = "blocker_dependency_owner_changed"
    BLOCKER_STATUS_CHANGED = "blocker_status_changed"
    BLOCKER_RESOLVED = "blocker_resolved"
    COMMITMENT_CREATED = "commitment_created"
    COMMITMENT_COMPLETED = "commitment_completed"
    COMMITMENT_MISSED = "commitment_missed"
    COMMITMENT_REVISED = "commitment_revised"
    ESCALATION_CREATED = "escalation_created"
    ESCALATION_APPROVED = "escalation_approved"
    ESCALATION_REJECTED = "escalation_rejected"
    ESCALATION_ACKNOWLEDGED = "escalation_acknowledged"
    ESCALATION_RESOLVED = "escalation_resolved"
    TASK_OWNER_CHANGED = "task_owner_changed"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_DEADLINE_CHANGED = "task_deadline_changed"
    PROJECT_OWNER_CHANGED = "project_owner_changed"
    PROJECT_TARGET_DATE_CHANGED = "project_target_date_changed"
    EMPLOYEE_MANAGER_CHANGED = "employee_manager_changed"


class MemoryFactStatus(StringEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"
    EXPIRED = "expired"


class MemoryPredicate(StringEnum):
    OWNS = "owns"
    RESPONSIBLE_FOR = "responsible_for"
    WORKING_ON = "working_on"
    DEPENDS_ON = "depends_on"
    BLOCKED_BY = "blocked_by"
    REQUIRES = "requires"
    MANAGED_BY = "managed_by"
    PART_OF_PROJECT = "part_of_project"
    COLLABORATES_WITH = "collaborates_with"
    WAITING_ON = "waiting_on"
    APPROVED_BY = "approved_by"
    RESOLVED_BY = "resolved_by"
    DECIDED_BY = "decided_by"
    AFFECTS = "affects"


class MemoryEpisodeType(StringEnum):
    BLOCKER = "blocker"
    RESOLUTION = "resolution"
    DECISION = "decision"
    DELIVERY = "delivery"
    INCIDENT = "incident"
    DEADLINE_CHANGE = "deadline_change"
    DEPENDENCY = "dependency"
    PROJECT_EVENT = "project_event"
    OTHER = "other"


class VisibilityScope(StringEnum):
    PRIVATE_1TO1 = "private_1to1"
    MANAGER_ONLY = "manager_only"
    PROJECT = "project"
    TEAM = "team"
    ORGANISATION = "organisation"


class MemoryJobStatus(StringEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ManagementProcedureStatus(StringEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETIRED = "retired"
