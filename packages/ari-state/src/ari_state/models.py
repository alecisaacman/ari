from __future__ import annotations

from datetime import date, datetime
from typing import Optional
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
    movement: Optional[bool] = None
    stress: Optional[int] = Field(default=None, ge=1, le=10)
    next_action: str = ""
    last_check_at: Optional[datetime] = None


class WeeklyState(ARIModel):
    week_start: date
    outcomes: list[str] = Field(default_factory=list, max_length=3)
    cannot_drift: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    lesson: str = ""
    last_review_at: Optional[datetime] = None


class OpenLoop(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: OpenLoopStatus = OpenLoopStatus.OPEN
    kind: OpenLoopKind = OpenLoopKind.TASK
    priority: OpenLoopPriority = OpenLoopPriority.MEDIUM
    source: str
    notes: str = ""
    project_id: Optional[UUID] = None
    opened_at: datetime
    due_at: Optional[datetime] = None
    last_touched_at: Optional[datetime] = None


class Project(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    slug: str
    name: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class Signal(ARIModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str
    severity: SignalSeverity
    summary: str
    reason: str
    evidence: list["EvidenceItem"] = Field(default_factory=list)
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    detected_at: datetime


class EvidenceItem(ARIModel):
    kind: str
    summary: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
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
    status: AlertStatus = AlertStatus.PENDING
    channel: AlertChannel
    escalation_level: AlertEscalationLevel = AlertEscalationLevel.VISIBLE
    title: str
    message: str
    reason: str
    source_signal_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    sent_at: Optional[datetime] = None
