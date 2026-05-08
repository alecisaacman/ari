from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ari_career_command import CareerCommandAdapter
from ari_surface_status import (
    SurfaceSeverity,
    SurfaceState,
    SurfaceStatus,
    SurfaceStatusStore,
    surface_status_from_telegram_event,
)
from ari_telegram_gateway.career_commands import handle_career_command_result
from ari_telegram_gateway.config import TelegramGatewayConfig
from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.models import AgentRole, IntentType
from ari_telegram_gateway.polling import run_polling

from tests.unit.test_career_command_adapter import (
    _career_root,
    _write_batch_summary,
    _write_tracker,
)
from tests.unit.test_telegram_gateway_polling import FakeTelegramClient


def test_surface_status_model_creation() -> None:
    status = SurfaceStatus(
        state=SurfaceState.WORKING,
        severity=SurfaceSeverity.INFO,
        title="ARI is working",
        message="Processing a Telegram update.",
        source="telegram",
        surface="telegram",
    )

    assert status.status_id.startswith("surface_status_")
    assert status.state is SurfaceState.WORKING
    assert status.severity is SurfaceSeverity.INFO


def test_surface_status_store_writes_current_and_history(tmp_path: Path) -> None:
    store = SurfaceStatusStore(tmp_path / "surface" / "status")
    status = SurfaceStatus(
        state=SurfaceState.SUCCESS,
        title="Stored",
        message="Status persisted.",
        source="test",
    )

    history_path = store.write(status)

    assert store.current_path.exists()
    assert history_path == store.history_dir / f"{status.status_id}.json"
    assert history_path.exists()
    current = json.loads(store.current_path.read_text(encoding="utf-8"))
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert current["status_id"] == status.status_id
    assert history["status_id"] == status.status_id


def test_telegram_pending_approval_event_maps_to_waiting_status() -> None:
    event = _builder().build_from_update(_telegram_update("Codex should inspect the repo"))

    status = surface_status_from_telegram_event(event)

    assert event.assigned_role is AgentRole.CTO_CODEX
    assert event.requires_approval is True
    assert status.state is SurfaceState.WAITING_FOR_APPROVAL
    assert status.severity is SurfaceSeverity.WARNING


def test_unauthorized_rejected_event_maps_to_blocked_status() -> None:
    event = _builder().build_from_update(_telegram_update("hello", sender_id=99))

    status = surface_status_from_telegram_event(event)

    assert event.authorized is False
    assert status.state is SurfaceState.BLOCKED
    assert status.severity is SurfaceSeverity.WARNING


def test_memory_capture_event_maps_to_success_status() -> None:
    event = _builder().build_from_update(_telegram_update("remember this useful context"))

    status = surface_status_from_telegram_event(event)

    assert event.normalized_intent is IntentType.MEMORY_CAPTURE
    assert status.state is SurfaceState.SUCCESS


def test_career_read_only_command_success_maps_to_success_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    adapter = CareerCommandAdapter(root=root)

    result = handle_career_command_result("/career tracker", adapter=adapter)

    assert result is not None
    assert result.surface_status.source == "career_command"
    assert result.surface_status.command == "tracker"
    assert result.surface_status.state is SurfaceState.SUCCESS


def test_career_scout_preview_maps_to_success_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    result = handle_career_command_result(
        "/career scout_preview",
        adapter=CareerCommandAdapter(root=root, runner=runner),
    )

    assert result is not None
    assert result.surface_status.command == "scout_preview"
    assert result.surface_status.state is SurfaceState.SUCCESS


def test_career_command_failure_maps_to_error_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="failed\n")

    result = handle_career_command_result(
        "/career save 1",
        adapter=CareerCommandAdapter(root=root, runner=runner),
    )

    assert result is not None
    assert result.surface_status.command == "save"
    assert result.surface_status.state is SurfaceState.ERROR
    assert result.surface_status.severity is SurfaceSeverity.ERROR


def test_career_missing_rows_maps_to_waiting_for_approval(tmp_path: Path) -> None:
    root = _career_root(tmp_path)

    result = handle_career_command_result("/career save", adapter=CareerCommandAdapter(root=root))

    assert result is not None
    assert result.surface_status.state is SurfaceState.WAITING_FOR_APPROVAL


def test_polling_writes_surface_status_for_career_command(tmp_path: Path, monkeypatch) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    monkeypatch.setenv("CAREER_COMMAND_ROOT", str(root))
    monkeypatch.setenv("ARI_SURFACE_STATUS_DIR", str(tmp_path / "surface" / "status"))
    client = FakeTelegramClient(updates=[[_telegram_update("/career tracker")]])

    run_polling(config=_config(tmp_path), client=client, max_updates=1)

    current = json.loads(
        (tmp_path / "surface" / "status" / "current.json").read_text(encoding="utf-8")
    )
    history_files = list((tmp_path / "surface" / "status" / "history").glob("*.json"))
    assert current["source"] == "career_command"
    assert current["command"] == "tracker"
    assert current["state"] == "success"
    assert len(history_files) == 2


def _builder() -> TelegramEventBuilder:
    return TelegramEventBuilder(
        bot_identity="ari_command",
        authorized_telegram_user_id="42",
        bot_id="bot-1",
        bot_username="AriCommandBot",
    )


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


def _telegram_update(text: str, *, sender_id: int = 42) -> dict:
    return {
        "update_id": 100,
        "message": {
            "message_id": 10,
            "date": 1_776_640_000,
            "from": {
                "id": sender_id,
                "is_bot": False,
                "first_name": "ARI",
                "username": "ari_owner",
            },
            "chat": {
                "id": sender_id,
                "type": "private",
            },
            "text": text,
        },
    }
