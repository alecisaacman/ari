from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ari_telegram_gateway.config import TelegramGatewayConfig
from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.persistence import TelegramEventStore, TelegramPollingStateStore
from ari_telegram_gateway.polling import run_polling


def test_polling_persists_last_processed_update_id(tmp_path) -> None:
    client = FakeTelegramClient(updates=[[_telegram_update(100)]])
    config = _config(tmp_path)

    run_polling(config=config, client=client, max_updates=1)

    state = json.loads(config.polling_state_file.read_text(encoding="utf-8"))
    assert state["last_processed_update_id"] == 100
    assert state["bot_identity"] == "ari_command"
    assert "updated_at" in state
    assert len(client.sent_messages) == 1


def test_polling_offset_resumes_from_persisted_update_id(tmp_path) -> None:
    config = _config(tmp_path)
    TelegramPollingStateStore(config.polling_state_file).save_processed_update(
        update_id=100,
        bot_identity=config.bot_identity,
    )
    client = FakeTelegramClient(updates=[[_telegram_update(101)]])

    run_polling(config=config, client=client, max_updates=1)

    assert client.get_updates_calls[0]["offset"] == 101
    state = json.loads(config.polling_state_file.read_text(encoding="utf-8"))
    assert state["last_processed_update_id"] == 101


def test_duplicate_update_id_is_skipped_without_reply(tmp_path) -> None:
    config = _config(tmp_path)
    TelegramPollingStateStore(config.polling_state_file).save_processed_update(
        update_id=100,
        bot_identity=config.bot_identity,
    )
    client = FakeTelegramClient(updates=[[_telegram_update(100)]])

    run_polling(config=config, client=client, max_updates=1)

    assert client.sent_messages == []
    assert list((tmp_path / "events").glob("*/*.json")) == []


def test_duplicate_update_does_not_create_duplicate_pending_codex_task(tmp_path) -> None:
    config = _config(tmp_path)
    store = TelegramEventStore(inbox_dir=config.inbox_dir, events_dir=config.events_dir)
    builder = TelegramEventBuilder(
        bot_identity=config.bot_identity,
        authorized_telegram_user_id=config.authorized_telegram_user_id,
        bot_id="bot-1",
        bot_username="AriCommandBot",
    )
    existing_event = builder.build_from_update(_telegram_update(100))
    store.save_event(existing_event)
    assert existing_event.pending_codex_task is not None
    store.save_codex_task(existing_event.pending_codex_task, event_id=existing_event.event_id)
    client = FakeTelegramClient(updates=[[_telegram_update(100)]])

    run_polling(config=config, client=client, max_updates=1)

    assert client.sent_messages == []
    event_files = [
        path for path in (tmp_path / "events").glob("*/*.json") if path.name.startswith("evt_")
    ]
    assert len(event_files) == 1
    assert len(list((tmp_path / "events" / "pending_codex_tasks").glob("*.json"))) == 1
    state = json.loads(config.polling_state_file.read_text(encoding="utf-8"))
    assert state["last_processed_update_id"] == 100


class FakeTelegramClient:
    def __init__(self, *, updates: list[list[dict[str, Any]]]) -> None:
        self.updates = updates
        self.get_updates_calls: list[dict[str, int | None]] = []
        self.sent_messages: list[dict[str, str]] = []

    def get_me(self) -> dict[str, Any]:
        return {"id": "bot-1", "username": "AriCommandBot"}

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        self.get_updates_calls.append({"offset": offset, "timeout": timeout})
        if not self.updates:
            return []
        return self.updates.pop(0)

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})

    def get_file(self, file_id: str) -> dict[str, Any]:
        return {"file_path": f"documents/{file_id}.txt"}

    def download_file(self, file_path: str, destination: Path) -> None:
        destination.write_text(file_path, encoding="utf-8")


def _config(tmp_path: Path) -> TelegramGatewayConfig:
    return TelegramGatewayConfig(
        telegram_bot_token="test-token",
        authorized_telegram_user_id="42",
        inbox_dir=tmp_path / "inbox",
        events_dir=tmp_path / "events",
        polling_state_file=tmp_path / "state" / "ari_command_polling_state.json",
        bot_identity="ari_command",
        polling_timeout_seconds=0,
    )


def _telegram_update(update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "date": 1_776_640_000,
            "from": {
                "id": 42,
                "is_bot": False,
                "first_name": "ARI",
                "username": "ari_owner",
            },
            "chat": {
                "id": 42,
                "type": "private",
            },
            "text": "Codex needs to inspect why dashboard buttons disappeared",
        },
    }
