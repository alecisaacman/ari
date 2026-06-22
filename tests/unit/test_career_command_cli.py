from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ari_core.ari import main

from tests.unit.test_career_command_adapter import (
    _career_root,
    _write_batch_summary,
    _write_pending,
    _write_scout_report,
    _write_tracker,
)


def test_career_command_center_cli_prints_operator_view_and_status(
    tmp_path: Path,
) -> None:
    root = _career_root(tmp_path)
    status_dir = tmp_path / "surface-status"
    _write_tracker(root)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")
    _write_scout_report(root)
    _write_batch_summary(root)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "career",
                "command-center",
                "--root",
                str(root),
                "--status-dir",
                str(status_dir),
            ]
        )

    assert exit_code == 0
    text = output.getvalue()
    assert "CAREER COMMAND CENTER" in text
    assert "Current objective: Get Alec hired" in text
    assert "TRACKER" in text
    assert "PENDING APPROVALS" in text
    assert "RECOMMENDED NEXT ACTIONS" in text
    current = json.loads((status_dir / "current.json").read_text(encoding="utf-8"))
    assert current["source"] == "career_command"
    assert current["state"] == "waiting_for_approval"
    assert current["metadata"]["command"] == "command-center"


def test_career_command_center_cli_json_is_structured(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_scout_report(root)
    _write_batch_summary(root)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["career", "command-center", "--root", str(root), "--json"])

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["objective"] == "Get Alec hired"
    assert payload["tracker"]["total_roles"] == 3
    assert payload["reports"]["latest_batch"]["total_count"] == 3
    assert payload["safety_boundary"]


def test_career_cli_read_commands_work_against_fake_root(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")
    _write_scout_report(root)
    _write_batch_summary(root)

    commands = ["status", "pending", "next", "tracker", "reports"]
    for command in commands:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["career", command, "--root", str(root)])
        assert exit_code == 0
        assert output.getvalue().strip()


def test_career_cli_missing_tracker_still_returns_useful_json(tmp_path: Path) -> None:
    root = _career_root(tmp_path)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["career", "tracker", "--root", str(root), "--json"])

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["exists"] is False
    assert payload["total_roles"] == 0
