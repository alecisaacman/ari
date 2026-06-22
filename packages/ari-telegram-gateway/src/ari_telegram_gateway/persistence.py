from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ari_telegram_gateway.models import PendingCodexTask, TelegramInboundEvent


class TelegramPollingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_processed_update_id: int
    updated_at: datetime
    bot_identity: str


class TelegramEventStore:
    def __init__(self, *, inbox_dir: Path, events_dir: Path) -> None:
        self.inbox_dir = inbox_dir.expanduser()
        self.events_dir = events_dir.expanduser()

    def save_raw_update(self, update: dict[str, Any]) -> Path:
        update_id = update.get("update_id", "unknown")
        path = self._daily_dir(self.inbox_dir) / f"telegram_update_{update_id}.json"
        self._write_json(path, update)
        return path

    def save_event(self, event: TelegramInboundEvent) -> Path:
        path = self._daily_dir(self.events_dir) / f"{event.event_id}.json"
        self._write_json(path, event.model_dump(mode="json"))
        return path

    def save_codex_task(self, task: PendingCodexTask, *, event_id: str) -> Path:
        path = self.events_dir / "pending_codex_tasks" / f"{task.task_id}.json"
        self._write_json(
            path,
            {
                "event_id": event_id,
                **task.model_dump(mode="json"),
            },
        )
        return path

    def has_processed_update(self, update_id: int) -> bool:
        for path in self.events_dir.glob("*/evt_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("raw_update_id") == update_id:
                return True
        return False

    def _daily_dir(self, base_dir: Path) -> Path:
        today = datetime.now(tz=UTC).date().isoformat()
        path = base_dir / today
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TelegramPollingStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def load(self, *, bot_identity: str) -> TelegramPollingState | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        state = TelegramPollingState.model_validate(payload)
        if state.bot_identity != bot_identity:
            return None
        return state

    def save_processed_update(self, *, update_id: int, bot_identity: str) -> TelegramPollingState:
        existing = self.load(bot_identity=bot_identity)
        if existing is not None and existing.last_processed_update_id > update_id:
            update_id = existing.last_processed_update_id
        state = TelegramPollingState(
            last_processed_update_id=update_id,
            updated_at=datetime.now(tz=UTC),
            bot_identity=bot_identity,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
        return state
