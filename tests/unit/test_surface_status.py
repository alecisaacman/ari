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
from ari_core.tux_companion import (
    CLICK_TARGET_ENV,
    TuxAssetError,
    build_bubble_text,
    build_tux_companion_config,
    discover_animation_frames,
    read_tux_companion_snapshot,
)
from ari_core.tux_status import TUX_ASSET_ROOT_ENV, TuxStatusAdapter, build_tux_status_preview
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


def test_tux_adapter_builds_preview_from_current_status(tmp_path: Path) -> None:
    status_dir = tmp_path / "surface" / "status"
    asset_root = tmp_path / "tux"
    _write_tux_assets(asset_root, tux_state="running", sprite_name="spritesheet.webp")
    SurfaceStatusStore(status_dir).write(
        build_surface_status(
            state=SurfaceState.WORKING,
            summary="ARI is running a local task.",
            source="test",
            event_id="evt_tux_preview",
        )
    )

    preview = TuxStatusAdapter(status_dir=status_dir, asset_root=asset_root).preview()

    assert preview.status_present is True
    assert preview.ari_state == "working"
    assert preview.tux_animation_state == "running"
    assert preview.summary == "ARI is running a local task."
    assert preview.sprite_path == str(asset_root / "final" / "spritesheet.webp")
    assert preview.frame_directory == str(asset_root / "frames" / "running")
    assert preview.frames_manifest_path == str(asset_root / "frames" / "frames-manifest.json")
    assert preview.assets_present is True
    assert preview.missing_assets == []
    assert preview.frame_width == 192
    assert preview.frame_height == 208


def test_tux_adapter_reports_missing_assets_without_real_asset_root(tmp_path: Path) -> None:
    status_dir = tmp_path / "surface" / "status"
    asset_root = tmp_path / "tux"
    SurfaceStatusStore(status_dir).write(
        build_surface_status(
            state=SurfaceState.WAITING_FOR_APPROVAL,
            summary="ARI needs approval.",
            source="test",
        )
    )

    preview = build_tux_status_preview(status_dir=status_dir, asset_root=asset_root)

    assert preview.ari_state == "waiting_for_approval"
    assert preview.tux_animation_state == "waiting"
    assert preview.assets_present is False
    assert preview.missing_assets == [
        "frames/waiting/",
        "final/spritesheet.png or final/spritesheet.webp",
        "frames/frames-manifest.json",
    ]


def test_tux_preview_cli_outputs_serializable_preview(tmp_path: Path) -> None:
    from ari_core.ari import main

    status_dir = tmp_path / "surface" / "status"
    asset_root = tmp_path / "tux"
    _write_tux_assets(asset_root, tux_state="review", sprite_name="spritesheet.png")
    SurfaceStatusStore(status_dir).write(
        build_surface_status(
            state=SurfaceState.REVIEWING,
            summary="ARI is reviewing an execution result.",
            source="test",
            event_id="evt_tux_cli",
        )
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "surface",
                "tux",
                "preview",
                "--status-dir",
                str(status_dir),
                "--asset-root",
                str(asset_root),
                "--json",
            ]
        )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["ari_state"] == "reviewing"
    assert payload["tux_animation_state"] == "review"
    assert payload["summary"] == "ARI is reviewing an execution result."
    assert payload["sprite_path"] == str(asset_root / "final" / "spritesheet.png")
    assert payload["frame_directory"] == str(asset_root / "frames" / "review")
    assert payload["assets_present"] is True


def test_tux_companion_config_resolves_env_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_root = tmp_path / "env-tux"
    status_dir = tmp_path / "env-status"
    monkeypatch.setenv(TUX_ASSET_ROOT_ENV, str(asset_root))
    monkeypatch.setenv(CLICK_TARGET_ENV, "http://127.0.0.1:3000")
    monkeypatch.setenv("ARI_SURFACE_STATUS_DIR", str(status_dir))

    config = build_tux_companion_config()

    assert config.asset_root == asset_root
    assert config.click_target == "http://127.0.0.1:3000"
    assert config.resolved_status_dir == status_dir
    assert config.poll_interval == 1.5
    assert config.show_bubble is True


def test_tux_companion_frame_discovery_loads_animation_state(tmp_path: Path) -> None:
    asset_root = tmp_path / "tux"
    frame_dir = asset_root / "frames" / "running"
    frame_dir.mkdir(parents=True)
    for frame_name in ["10.png", "02.png", "01.png"]:
        (frame_dir / frame_name).write_bytes(b"fake frame")

    frames = discover_animation_frames(asset_root, "running")

    assert frames.state == "running"
    assert [path.name for path in frames.frame_paths] == ["01.png", "02.png", "10.png"]


def test_tux_companion_snapshot_uses_status_animation_and_bubble(tmp_path: Path) -> None:
    status_dir = tmp_path / "surface" / "status"
    asset_root = tmp_path / "tux"
    _write_tux_assets(asset_root, tux_state="running", sprite_name="spritesheet.png")
    _write_tux_animation_frames(asset_root, "running", count=2)
    SurfaceStatusStore(status_dir).write(
        build_surface_status(
            state=SurfaceState.WORKING,
            summary="ARI is running a local task.",
            source="test",
        )
    )
    config = build_tux_companion_config(asset_root=asset_root, status_dir=status_dir)

    snapshot = read_tux_companion_snapshot(config)

    assert snapshot.preview.ari_state == "working"
    assert snapshot.preview.tux_animation_state == "running"
    assert snapshot.frames.state == "running"
    assert len(snapshot.frames.frame_paths) == 2
    assert snapshot.bubble_text == "working · running\nARI is running a local task."


def test_tux_companion_missing_assets_are_reported_cleanly(tmp_path: Path) -> None:
    asset_root = tmp_path / "tux"

    with pytest.raises(TuxAssetError) as exc:
        discover_animation_frames(asset_root, "waiting")

    assert "Tux animation frame directory is missing" in str(exc.value)
    assert exc.value.missing_assets == ["frames/waiting/"]


def test_tux_companion_bubble_defaults_missing_status_to_idle(tmp_path: Path) -> None:
    asset_root = tmp_path / "tux"
    _write_tux_assets(asset_root, tux_state="idle", sprite_name="spritesheet.png")
    preview = build_tux_status_preview(
        status_dir=tmp_path / "surface" / "status",
        asset_root=asset_root,
    )

    assert build_bubble_text(preview) == "idle · idle\nNo current ARI surface status found."


def test_tux_companion_dry_run_cli_outputs_selected_frames(tmp_path: Path) -> None:
    from ari_core.ari import main

    status_dir = tmp_path / "surface" / "status"
    asset_root = tmp_path / "tux"
    _write_tux_assets(asset_root, tux_state="waiting", sprite_name="spritesheet.png")
    _write_tux_animation_frames(asset_root, "waiting", count=2)
    SurfaceStatusStore(status_dir).write(
        build_surface_status(
            state=SurfaceState.WAITING_FOR_APPROVAL,
            summary="Codex needs approval.",
            source="test",
        )
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "surface",
                "tux",
                "companion",
                "--status-dir",
                str(status_dir),
                "--asset-root",
                str(asset_root),
                "--dry-run",
            ]
        )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert payload["ari_state"] == "waiting_for_approval"
    assert payload["tux_animation_state"] == "waiting"
    assert payload["bubble_text"] == "waiting_for_approval · waiting\nCodex needs approval."
    assert payload["selected_frame_count"] == 2


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


def _write_tux_assets(
    asset_root: Path,
    *,
    tux_state: str,
    sprite_name: str = "spritesheet.png",
) -> None:
    (asset_root / "frames" / tux_state).mkdir(parents=True)
    (asset_root / "final").mkdir(parents=True)
    (asset_root / "final" / sprite_name).write_bytes(b"fake sprite")
    (asset_root / "frames" / "frames-manifest.json").write_text(
        '{"frames":[]}\n',
        encoding="utf-8",
    )


def _write_tux_animation_frames(asset_root: Path, tux_state: str, *, count: int) -> None:
    frame_dir = asset_root / "frames" / tux_state
    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame_index in range(count):
        (frame_dir / f"{frame_index:02d}.png").write_bytes(b"fake frame")
