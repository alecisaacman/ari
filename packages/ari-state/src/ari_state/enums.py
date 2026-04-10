from enum import Enum


class OpenLoopStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CLOSED = "closed"


class OpenLoopKind(str, Enum):
    TASK = "task"
    QUESTION = "question"
    COMMITMENT = "commitment"
    FOLLOW_UP = "follow_up"


class OpenLoopPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SignalSeverity(str, Enum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class EventCategory(str, Enum):
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


class AlertStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class AlertChannel(str, Enum):
    HUB = "hub"
    TERMINAL = "terminal"
    PHONE = "phone"
    NOTIFICATION = "notification"


class AlertEscalationLevel(str, Enum):
    VISIBLE = "visible"
    ELEVATED = "elevated"
    INTERRUPTIVE = "interruptive"
    URGENT = "urgent"
