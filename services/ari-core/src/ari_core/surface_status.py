from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_SURFACE_STATUS_DIR = Path("data/surface/status")


class SurfaceState(StrEnum):
    IDLE = "idle"
    ROUTING = "routing"
    WORKING = "working"
    REVIEWING = "reviewing"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    BLOCKED = "blocked"
    ERROR = "error"
    SUCCESS = "success"


TUX_STATE_BY_SURFACE_STATE: dict[SurfaceState, str] = {
    SurfaceState.IDLE: "idle",
    SurfaceState.ROUTING: "jumping",
    SurfaceState.WORKING: "running",
    SurfaceState.REVIEWING: "review",
    SurfaceState.WAITING_FOR_APPROVAL: "waiting",
    SurfaceState.BLOCKED: "failed",
    SurfaceState.ERROR: "failed",
    SurfaceState.SUCCESS: "waving",
}


def new_surface_event_id() -> str:
    return f"evt_{uuid4().hex}"


def now_utc() -> datetime:
    return datetime.now(tz=UTC).replace(microsecond=0)


class SurfaceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: SurfaceState
    role: str = "ARI"
    source: str = "system"
    summary: str
    event_id: str = Field(default_factory=new_surface_event_id)
    task_id: str | None = None
    updated_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role", "source", "summary", "event_id")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @property
    def tux_state(self) -> str:
        return TUX_STATE_BY_SURFACE_STATE[self.state]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SurfaceStatusStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        configured_root = root_dir or Path(
            os.environ.get("ARI_SURFACE_STATUS_DIR", str(DEFAULT_SURFACE_STATUS_DIR))
        )
        self.root_dir = configured_root.expanduser()
        self.current_path = self.root_dir / "current.json"
        self.history_dir = self.root_dir / "history"

    def write(self, status: SurfaceStatus) -> Path:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.current_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(status.to_dict(), indent=2, sort_keys=True) + "\n"
        history_path = self._history_path(status)
        _atomic_write_text(history_path, payload)
        _atomic_write_text(self.current_path, payload)
        return history_path

    def load_current(self) -> SurfaceStatus | None:
        if not self.current_path.exists():
            return None
        return SurfaceStatus.model_validate_json(self.current_path.read_text(encoding="utf-8"))

    def _history_path(self, status: SurfaceStatus) -> Path:
        event_id = _filename_safe(status.event_id)
        history_path = self.history_dir / f"{event_id}.json"
        if not history_path.exists():
            return history_path
        timestamp = status.updated_at.strftime("%Y%m%dT%H%M%SZ")
        history_path = self.history_dir / f"{timestamp}_{event_id}.json"
        if not history_path.exists():
            return history_path
        return self.history_dir / f"{timestamp}_{event_id}_{uuid4().hex}.json"


def write_surface_status(
    status: SurfaceStatus,
    *,
    root_dir: Path | None = None,
) -> Path:
    return SurfaceStatusStore(root_dir=root_dir).write(status)


def read_current_surface_status(*, root_dir: Path | None = None) -> SurfaceStatus | None:
    return SurfaceStatusStore(root_dir=root_dir).load_current()


def build_surface_status(
    *,
    state: SurfaceState | str,
    summary: str,
    role: str = "ARI",
    source: str = "system",
    event_id: str | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SurfaceStatus:
    payload: dict[str, Any] = {
        "state": state,
        "role": role,
        "source": source,
        "summary": summary,
        "task_id": task_id,
        "metadata": metadata or {},
    }
    if event_id is not None:
        payload["event_id"] = event_id
    return SurfaceStatus.model_validate(payload)


def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _filename_safe(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value
    )
