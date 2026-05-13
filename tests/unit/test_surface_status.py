from __future__ import annotations

import json
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest
from ari_core.surface_status import (
    TUX_STATE_BY_SURFACE_STATE,
    SurfaceState,
    SurfaceStatus,
    SurfaceStatusStore,
    build_surface_status,
)
from ari_surface_status import surface_status_from_telegram_event
from ari_telegram_gateway.career_commands import handle_career_command_result
from ari_telegram_gateway.config import TelegramGatewayConfig
from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.models import AgentRole, IntentType
from ari_telegram_gateway.polling import run_polling
from pydantic import ValidationError

from tests.unit.test_career_command_adapter import (
    _career_root,
    _write_batch_summary,
    _write_tracker,
)
from tests.unit.test_telegram_gateway_polling import FakeTelegramClient


def test_surface_status_model_matches_canonical_contract() -> None:
    status = SurfaceStatus(
        state=SurfaceState.WORKING,
        summary="ARI is working.",
        source="test",
        event_id="evt_test",
        metadata={"surface": "tux"},
    )

    assert status.to_dict() == {
        "event_id": "evt_test",
        "metadata": {"surface": "tux"},
        "role": "ARI",
        "source": "test",
        "state": "working",
        "summary": "ARI is working.",
        "task_id": None,
        "updated_at": status.updated_at.isoformat().replace("+00:00", "Z"),
    }
    assert status.tux_state == "running"


def test_surface_status_rejects_unsupported_state() -> None:
    with pytest.raises(ValidationError):
        build_surface_status(state="thinking", summary="Legacy state is not supported.")


def test_tux_state_mapping_covers_every_surface_state() -> None:
    assert TUX_STATE_BY_SURFACE_STATE == {
        SurfaceState.IDLE: "idle",
        SurfaceState.ROUTING: "jumping",
        SurfaceState.WORKING: "running",
        SurfaceState.REVIEWING: "review",
        SurfaceState.WAITING_FOR_APPROVAL: "waiting",
        SurfaceState.BLOCKED: "failed",
        SurfaceState.ERROR: "failed",
        SurfaceState.SUCCESS: "waving",
    }


def test_surface_status_store_writes_current_and_history_atomically(tmp_path: Path) -> None:
    store = SurfaceStatusStore(tmp_path / "surface" / "status")
    status = SurfaceStatus(
        state=SurfaceState.SUCCESS,
        summary="Status persisted.",
        source="test",
        event_id="evt_store_test",
    )

    history_path = store.write(status)

    assert store.current_path.exists()
    assert history_path == store.history_dir / "evt_store_test.json"
    assert history_path.exists()
    current = json.loads(store.current_path.read_text(encoding="utf-8"))
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert current["event_id"] == "evt_store_test"
    assert history == current
    assert store.load_current() == status
    assert not list(store.root_dir.rglob("*.tmp"))


def test_surface_status_cli_set_and_show(tmp_path: Path) -> None:
    from ari_core.ari import main

    status_dir = tmp_path / "surface" / "status"
    set_output = StringIO()
    with redirect_stdout(set_output):
        exit_code = main(
            [
                "surface",
                "status",
                "set",
                "--state",
                "working",
                "--summary",
                "Testing Tux status",
                "--source",
                "test",
                "--event-id",
                "evt_cli_test",
                "--metadata-json",
                '{"surface":"tux"}',
                "--status-dir",
                str(status_dir),
            ]
        )
    assert exit_code == 0

    show_output = StringIO()
    with redirect_stdout(show_output):
        main(
            [
                "surface",
                "status",
                "show",
                "--status-dir",
                str(status_dir),
            ]
        )
    written = json.loads(set_output.getvalue())
    shown = json.loads(show_output.getvalue())
    assert written == shown
    assert shown["state"] == "working"
    assert shown["summary"] == "Testing Tux status"
    assert shown["metadata"] == {"surface": "tux"}


def test_telegram_pending_approval_event_maps_to_waiting_status() -> None:
    event = _builder().build_from_update(_telegram_update("Codex should inspect the repo"))

    status = surface_status_from_telegram_event(event)

    assert event.assigned_role is AgentRole.CTO_CODEX
    assert event.requires_approval is True
    assert status.state is SurfaceState.WAITING_FOR_APPROVAL
    assert status.task_id == event.pending_codex_task.task_id


def test_unauthorized_rejected_event_maps_to_blocked_status() -> None:
    event = _builder().build_from_update(_telegram_update("hello", sender_id=99))

    status = surface_status_from_telegram_event(event)

    assert event.authorized is False
    assert status.state is SurfaceState.BLOCKED


def test_memory_capture_event_maps_to_success_status() -> None:
    event = _builder().build_from_update(_telegram_update("remember this useful context"))

    status = surface_status_from_telegram_event(event)

    assert event.normalized_intent is IntentType.MEMORY_CAPTURE
    assert status.state is SurfaceState.SUCCESS


def test_career_read_only_command_success_maps_to_success_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    adapter = _career_adapter(root)

    result = handle_career_command_result("/career tracker", adapter=adapter)

    assert result is not None
    assert result.surface_status.source == "career_command"
    assert result.surface_status.metadata["command"] == "tracker"
    assert result.surface_status.state is SurfaceState.SUCCESS


def test_career_scout_preview_maps_to_success_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    result = handle_career_command_result(
        "/career scout_preview",
        adapter=_career_adapter(root, runner=runner),
    )

    assert result is not None
    assert result.surface_status.metadata["command"] == "scout_preview"
    assert result.surface_status.state is SurfaceState.SUCCESS


def test_career_command_failure_maps_to_error_status(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)

    def runner(command, cwd):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="failed\n")

    result = handle_career_command_result(
        "/career save 1",
        adapter=_career_adapter(root, runner=runner),
    )

    assert result is not None
    assert result.surface_status.metadata["command"] == "save"
    assert result.surface_status.state is SurfaceState.ERROR


def test_career_missing_rows_maps_to_waiting_for_approval(tmp_path: Path) -> None:
    root = _career_root(tmp_path)

    result = handle_career_command_result("/career save", adapter=_career_adapter(root))

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
    assert current["metadata"]["command"] == "tracker"
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


def _career_adapter(root: Path, runner=None):
    from ari_career_command import CareerCommandAdapter

    if runner is None:
        return CareerCommandAdapter(root=root)
    return CareerCommandAdapter(root=root, runner=runner)
