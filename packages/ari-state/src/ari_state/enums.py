from enum import StrEnum


class OpenLoopStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CLOSED = "closed"


class OpenLoopKind(StrEnum):
    TASK = "task"
    QUESTION = "question"
    COMMITMENT = "commitment"
    FOLLOW_UP = "follow_up"
    JOB_APPLICATION = "job_application"


class OpenLoopPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(StrEnum):
    READ_FILE = "READ_FILE"
    RUN_COMMAND = "RUN_COMMAND"
    ASK_USER = "ASK_USER"
    EDIT_FILE = "EDIT_FILE"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SignalSeverity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class EventCategory(StrEnum):
    DAILY_UPDATE = "daily_update"
    WEEKLY_PLANNING = "weekly_planning"
    WEEKLY_REFLECTION = "weekly_reflection"
    OPEN_LOOP_ADD = "open_loop_add"
    OPEN_LOOP_UPDATE = "open_loop_update"
    OPEN_LOOP_RESOLVE = "open_loop_resolve"
    PROJECT_UPDATE = "project_update"
    SIGNAL_GENERATED = "signal_generated"
    ALERT_GENERATED = "alert_generated"
    CAPTURE = "capture"
    INTELLIGENCE_ITEM = "intelligence_item"


class AlertStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class AlertChannel(StrEnum):
    HUB = "hub"
    TERMINAL = "terminal"
    PHONE = "phone"
    NOTIFICATION = "notification"


class AlertEscalationLevel(StrEnum):
    VISIBLE = "visible"
    ELEVATED = "elevated"
    INTERRUPTIVE = "interruptive"
    URGENT = "urgent"


class DecisionType(StrEnum):
    ACT = "act"
    RESPOND = "respond"
    DEFER = "defer"


class AuthorityOutcome(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
    DEFER = "defer"


class VerificationOutcome(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    ASK_USER = "ask_user"
    SKIPPED = "skipped"


class ControlOutcome(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    REQUIRE_APPROVAL = "require_approval"
    DENIED = "denied"
    DEFERRED = "deferred"


class ControllerCycleState(StrEnum):
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RESUMED = "resumed"
    DENIED = "denied"
    COMPLETED = "completed"
    FAILED = "failed"


class PendingApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ControllerEventType(StrEnum):
    OBSERVATION_INTAKE = "observation_intake"
    DECISION_SELECTED = "decision_selected"
    AUTHORITY_RESULT = "authority_result"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    CONTROLLER_RESUMED = "controller_resumed"
    DISPATCH_STARTED = "dispatch_started"
    DISPATCH_RESULT = "dispatch_result"
    VERIFICATION_RESULT = "verification_result"
    CONTROLLER_OUTCOME = "controller_outcome"


class SkillRegistrationKind(StrEnum):
    """How a registered skill's tools are reached. Only MCP exists today;
    this stays an enum (not a free string) so adding a second kind later is
    a one-line addition here, not a new column."""

    MCP = "mcp"


class SkillKind(StrEnum):
    """Where a single skill invocation came from, for audit purposes.
    CUSTOM_TOOL = dispatched in-process via make_tool_dispatcher.
    WEB_SEARCH / MCP = resolved server-side by Anthropic before the
    response reaches ARI at all — see SkillInvocation for why that matters
    for what can and can't be audited."""

    CUSTOM_TOOL = "custom_tool"
    WEB_SEARCH = "web_search"
    MCP = "mcp"
