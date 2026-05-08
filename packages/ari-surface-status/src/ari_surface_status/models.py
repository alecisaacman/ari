from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SurfaceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    BLOCKED = "blocked"
    SUCCESS = "success"
    ERROR = "error"


class SurfaceSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _status_id() -> str:
    return f"surface_status_{uuid4().hex}"


class SurfaceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_id: str = Field(default_factory=_status_id)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    state: SurfaceState
    severity: SurfaceSeverity = SurfaceSeverity.INFO
    title: str
    message: str
    source: str
    surface: str | None = None
    event_id: str | None = None
    command: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
