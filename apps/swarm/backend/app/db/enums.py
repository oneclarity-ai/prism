from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    member = "member"


class AgentStatus(StrEnum):
    active = "active"
    paused = "paused"


class ToolGrant(StrEnum):
    allowed = "allowed"
    ask_first = "ask_first"
    off = "off"


class Environment(StrEnum):
    local = "local"
    dev = "dev"
    staging = "staging"
    production = "production"


class TaskStatus(StrEnum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    failed = "failed"


class RunTrigger(StrEnum):
    manual = "manual"
    schedule = "schedule"
    retry = "retry"
    approval = "approval"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    waiting_children = "waiting_children"  # parallel run: sub-agents are working
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class RunKind(StrEnum):
    single = "single"  # one agent does the whole task
    orchestrator = "orchestrator"  # plans sub-agents, then merges their results
    child = "child"  # one sub-agent of a parallel run


class RunEventType(StrEnum):
    message = "message"
    tool_call = "tool_call"
    tool_result = "tool_result"
    status = "status"
    log = "log"


class ArtifactKind(StrEnum):
    screenshot = "screenshot"
    report = "report"
    test_script = "test_script"
    trace = "trace"
    frame = "frame"  # live view of a computer, only the latest few are kept
    file = "file"  # a file the agent made for the user (csv, md, downloads)


class TestCaseStatus(StrEnum):
    pending = "pending"
    passed = "pass"
    failed = "fail"
    blocked = "blocked"
    skipped = "skipped"


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class BugStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    filed = "filed"
    rejected = "rejected"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
