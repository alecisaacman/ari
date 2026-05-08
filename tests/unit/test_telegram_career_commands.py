from __future__ import annotations

import subprocess
from pathlib import Path

from ari_career_command import CareerCommandAdapter
from ari_telegram_gateway.career_commands import handle_career_command
from ari_telegram_gateway.config import TelegramGatewayConfig
from ari_telegram_gateway.polling import run_polling

from tests.unit.test_career_command_adapter import (
    _career_root,
    _write_batch_summary,
    _write_markdown,
    _write_pending,
    _write_scout_report,
    _write_tracker,
)
from tests.unit.test_telegram_gateway_polling import FakeTelegramClient


def test_telegram_command_routing_recognizes_career_commands(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_pending(root, "pending.md", "Pending Action: Alpha outreach")
    _write_scout_report(root)
    _write_batch_summary(root)
    adapter = CareerCommandAdapter(root=root)

    assert "Career Command status" in handle_career_command("/career status", adapter=adapter)
    assert "Top tracked opportunities" in handle_career_command("/career tracker", adapter=adapter)
    assert "Pending Career Command drafts" in handle_career_command(
        "/career pending", adapter=adapter
    )
    latest_response = handle_career_command("/career latest", adapter=adapter)
    assert latest_response is not None
    assert "Latest Career Command output" in latest_response
    assert "Career Command dashboard" in handle_career_command("/career dashboard", adapter=adapter)
    assert handle_career_command("career status", adapter=adapter) is None


def test_career_help_lists_operations_and_safety(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    response = handle_career_command("/career help", adapter=CareerCommandAdapter(root=root))

    assert response is not None
    assert "/career scout_preview" in response
    assert "/career save <rows>" in response
    assert "/career draft <rows>" in response
    assert "/career approve <pending_id_or_filename>" in response
    assert "No applications" in response
    assert "external contact" in response


def test_scout_preview_route_does_not_save_apply_or_send(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    adapter = CareerCommandAdapter(root=root, runner=runner)

    response = handle_career_command("/career scout_preview", adapter=adapter)

    assert response is not None
    assert "Stopped for review" in response
    assert "No jobs saved" in response
    assert calls == [
        [str(root / ".venv" / "bin" / "python"), "career_scout.py"],
        [str(root / ".venv" / "bin" / "python"), "tools/scout_report_to_jobs.py"],
        [
            str(root / ".venv" / "bin" / "python"),
            "tools/batch_evaluate_jobs.py",
            "--limit",
            "5",
        ],
    ]
    command_text = " ".join(" ".join(command) for command in calls)
    assert "save_from_batch_summary" not in command_text
    assert "batch_draft_outreach" not in command_text
    assert "apply" not in command_text


def test_save_route_parses_rows_safely(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(command, 0, stdout="Saved 2 row(s)\n", stderr="")

    response = handle_career_command(
        "/career save 1-2",
        adapter=CareerCommandAdapter(root=root, runner=runner),
    )

    assert response is not None
    assert "Career save: ok" in response
    assert "local tracker only" in response
    assert calls == [
        [
            str(root / ".venv" / "bin" / "python"),
            "tools/save_from_batch_summary.py",
            "--rows",
            "1,2",
        ]
    ]


def test_draft_route_parses_rows_safely(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(
            command, 0, stdout="Created pending actions:\n", stderr=""
        )

    response = handle_career_command(
        "/career draft 1, 3",
        adapter=CareerCommandAdapter(root=root, runner=runner),
    )

    assert response is not None
    assert "Career draft: ok" in response
    assert "pending outreach drafts only" in response
    assert calls == [
        [
            str(root / ".venv" / "bin" / "python"),
            "tools/batch_draft_outreach.py",
            "--rows",
            "1,3",
        ]
    ]


def test_invalid_row_specs_fail_safely_from_telegram(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    response = handle_career_command(
        "/career save 1;rm -rf",
        adapter=CareerCommandAdapter(root=root, runner=runner),
    )

    assert response is not None
    assert response.startswith("Career Command error:")
    assert calls == []


def test_approve_and_reject_routes_update_local_pending_state(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")
    _write_pending(root, "20260501_outreach_beta.md", "Pending Action: Beta outreach")
    adapter = CareerCommandAdapter(root=root)

    approve_response = handle_career_command(
        "/career approve 20260501_outreach_alpha",
        adapter=adapter,
    )
    reject_response = handle_career_command(
        "/career reject 20260501_outreach_beta.md",
        adapter=adapter,
    )

    assert approve_response is not None
    assert "Approved local pending action." in approve_response
    assert reject_response is not None
    assert "Rejected local pending action." in reject_response
    assert (root / "approved_actions" / "20260501_outreach_alpha.md").exists()
    assert (root / "rejected_actions" / "20260501_outreach_beta.md").exists()


def test_invalid_pending_id_fails_safely_from_telegram(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")

    response = handle_career_command(
        "/career approve ../20260501_outreach_alpha.md",
        adapter=CareerCommandAdapter(root=root),
    )

    assert response is not None
    assert response.startswith("Career Command error:")
    assert (root / "pending_actions" / "20260501_outreach_alpha.md").exists()


def test_no_external_send_apply_contact_commands_exist_in_telegram_routes(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_batch_summary(root)
    _write_markdown(root / "pending_actions" / "20260501_outreach_alpha.md", "# Pending")
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    adapter = CareerCommandAdapter(root=root, runner=runner)
    handle_career_command("/career save 1", adapter=adapter)
    handle_career_command("/career draft 1", adapter=adapter)
    handle_career_command("/career scout_preview", adapter=adapter)
    handle_career_command("/career approve 20260501_outreach_alpha", adapter=adapter)

    command_text = " ".join(" ".join(command[1:]) for command in calls).lower()
    assert "send" not in command_text
    assert "apply" not in command_text
    assert "contact" not in command_text
    assert "browser" not in command_text


def test_polling_replies_to_career_status_command(tmp_path: Path, monkeypatch) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_pending(root, "pending.md", "Pending Action: Alpha outreach")
    _write_scout_report(root)
    _write_batch_summary(root)
    monkeypatch.setenv("CAREER_COMMAND_ROOT", str(root))
    config = TelegramGatewayConfig(
        telegram_bot_token="test-token",
        authorized_telegram_user_id="42",
        inbox_dir=tmp_path / "inbox",
        events_dir=tmp_path / "events",
        polling_state_file=tmp_path / "state" / "ari_command_polling_state.json",
        bot_identity="ari_command",
        polling_timeout_seconds=0,
    )
    client = FakeTelegramClient(updates=[[_telegram_update("/career status")]])

    run_polling(config=config, client=client, max_updates=1)

    assert len(client.sent_messages) == 1
    assert "Career Command status" in client.sent_messages[0]["text"]
    assert "Tracked opportunities: 3" in client.sent_messages[0]["text"]


def _telegram_update(text: str) -> dict:
    return {
        "update_id": 100,
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
            "text": text,
        },
    }
