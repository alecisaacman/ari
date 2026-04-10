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


class OpenLoopPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
