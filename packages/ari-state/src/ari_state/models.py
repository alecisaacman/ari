from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ari_state.enums import (
    AlertChannel,
    AlertEscalationLevel,
    AlertStatus,
    EventCategory,
    OpenLoopKind,
    OpenLoopPriority,
    OpenLoopStatus,
    ProjectStatus,
    SignalSeverity,
)


class ARIModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class DailyState(ARIModel):
    date: date
    priorities: list[str] = Field(default_factory=list, max_length=3)
    win_condition: str = ""
    movement: bool | None = None
    stress: int | None = Field(default=None, ge=1, le=10)
    next_action: str = ""
    last_check_at: datetime | None = None


class WeeklyState(ARIModel):
    week_start: date
    outcomes: list[str] = Field(default_factory=list, max_length=3)
    cannot_drift: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    lesson: str = ""
    last_review_at: datetime | None = None


class OpenLoop(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: OpenLoopStatus = OpenLoopStatus.OPEN
    kind: OpenLoopKind = OpenLoopKind.TASK
    priority: OpenLoopPriority = OpenLoopPriority.MEDIUM
    source: str
    notes: str = ""
    project_id: UUID | None = None
    opened_at: datetime
    due_at: datetime | None = None
    last_touched_at: datetime | None = None


class Project(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    slug: str
    name: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class Signal(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    state_date: date | None = None
    kind: str
    fingerprint: str = ""
    severity: SignalSeverity
    summary: str
    reason: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    related_entity_type: str | None = None
    related_entity_id: UUID | None = None
    detected_at: datetime


class EvidenceItem(ARIModel):
    kind: str
    summary: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class Event(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    source: str
    category: EventCategory = EventCategory.CAPTURE
    occurred_at: datetime
    title: str
    body: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    normalized_text: str = ""


class Alert(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    state_date: date | None = None
    fingerprint: str = ""
    status: AlertStatus = AlertStatus.PENDING
    channel: AlertChannel
    escalation_level: AlertEscalationLevel = AlertEscalationLevel.VISIBLE
    title: str
    message: str
    reason: str
    source_signal_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    sent_at: datetime | None = None


class OrchestrationRun(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    state_date: date
    state_fingerprint: str
    executed_at: datetime
    signal_ids: list[UUID] = Field(default_factory=list)
    alert_ids: list[UUID] = Field(default_factory=list)
