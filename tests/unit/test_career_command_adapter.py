from __future__ import annotations

import csv
import subprocess
from pathlib import Path

from ari_career_command import CareerCommandAdapter


def test_status_reads_tracker_and_action_counts(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_pending(root, "draft-a.md", "Pending Action: Alpha outreach")
    _write_markdown(root / "approved_actions" / "approved.md", "# Approved")
    _write_markdown(root / "rejected_actions" / "rejected.md", "# Rejected")
    _write_scout_report(root)
    _write_batch_summary(root)

    status = CareerCommandAdapter(root=root).career_status()

    assert status.root_exists is True
    assert status.python_exists is True
    assert status.tracker_count == 3
    assert status.pending_count == 1
    assert status.approved_count == 1
    assert status.rejected_count == 1
    assert status.latest_scout_report_exists is True
    assert status.latest_batch_summary_exists is True


def test_tracker_summary_ranks_opportunities_by_score(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)

    summary = CareerCommandAdapter(root=root).career_tracker_summary(limit=2)

    assert summary.total_count == 3
    assert [item.company for item in summary.opportunities] == ["Beta", "Alpha"]
    assert summary.opportunities[0].overall_score == 8.3


def test_pending_summary_lists_pending_drafts(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")

    summary = CareerCommandAdapter(root=root).career_pending_actions_summary()

    assert summary.total_count == 1
    assert summary.drafts[0].filename == "20260501_outreach_alpha.md"
    assert summary.drafts[0].title == "Pending Action: Alpha outreach"
    assert summary.drafts[0].action_type == "outreach"
    assert summary.drafts[0].status == "pending"


def test_latest_batch_summary_parses_csv(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)

    summary = CareerCommandAdapter(root=root).career_latest_batch_summary(limit=2)

    assert summary.exists is True
    assert summary.total_count == 3
    assert [item.company for item in summary.opportunities] == ["Meridian", "Corner"]
    assert summary.opportunities[0].overall_score == 8.0


def test_dashboard_info_returns_expected_run_command(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    (root / "ace_career_dashboard.py").write_text("print('dashboard')\n", encoding="utf-8")

    info = CareerCommandAdapter(root=root).career_dashboard_info()

    assert info.exists is True
    assert info.local_url == "http://localhost:8501"
    assert str(root) in info.run_command
    assert str(root / ".venv" / "bin" / "python") in info.run_command
    assert "streamlit run ace_career_dashboard.py" in info.run_command


def test_scout_preview_runs_only_safe_pipeline_commands(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    adapter = CareerCommandAdapter(root=root, runner=runner)

    results = adapter.run_daily_scout_pipeline_preview()

    assert [result.ok for result in results] == [True, True, True]
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
    disallowed = " ".join(" ".join(command) for command in calls)
    assert "save_from_batch_summary" not in disallowed
    assert "batch_draft_outreach" not in disallowed
    assert "review_pending_actions" not in disallowed
    assert "update_status" not in disallowed


def test_save_batch_rows_parses_row_specs_safely(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(command, 0, stdout="Saved 2 row(s)\n", stderr="")

    result = CareerCommandAdapter(root=root, runner=runner).save_batch_rows_to_tracker("1-2")

    assert result.ok
    assert calls == [
        [
            str(root / ".venv" / "bin" / "python"),
            "tools/save_from_batch_summary.py",
            "--rows",
            "1,2",
        ]
    ]


def test_draft_tracker_rows_parses_row_specs_safely(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == root
        return subprocess.CompletedProcess(
            command, 0, stdout="Created pending actions:\n", stderr=""
        )

    result = CareerCommandAdapter(root=root, runner=runner).draft_outreach_for_tracker_rows("1, 3")

    assert result.ok
    assert calls == [
        [
            str(root / ".venv" / "bin" / "python"),
            "tools/batch_draft_outreach.py",
            "--rows",
            "1,3",
        ]
    ]


def test_invalid_row_specs_fail_safely_without_running_commands(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    adapter = CareerCommandAdapter(root=root, runner=runner)

    for rows in ["1;rm -rf", "4", "3-1", ""]:
        try:
            adapter.save_batch_rows_to_tracker(rows)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid rows to fail: {rows}")

    assert calls == []


def test_approve_pending_action_moves_file_and_logs_local_state(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")

    result = CareerCommandAdapter(root=root).approve_pending_action("20260501_outreach_alpha")

    assert result.status == "approved"
    assert not (root / "pending_actions" / "20260501_outreach_alpha.md").exists()
    approved_path = root / "approved_actions" / "20260501_outreach_alpha.md"
    assert approved_path.exists()
    assert "**Status:** approved" in approved_path.read_text(encoding="utf-8")
    log_rows = _read_action_log(root)
    assert log_rows[-1]["action_id"] == "20260501_outreach_alpha"
    assert log_rows[-1]["status"] == "approved"


def test_reject_pending_action_moves_file_and_logs_local_state(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_beta.md", "Pending Action: Beta outreach")

    result = CareerCommandAdapter(root=root).reject_pending_action("20260501_outreach_beta.md")

    assert result.status == "rejected"
    rejected_path = root / "rejected_actions" / "20260501_outreach_beta.md"
    assert rejected_path.exists()
    assert "**Status:** rejected" in rejected_path.read_text(encoding="utf-8")
    log_rows = _read_action_log(root)
    assert log_rows[-1]["action_id"] == "20260501_outreach_beta"
    assert log_rows[-1]["status"] == "rejected"


def test_invalid_pending_ids_fail_safely(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_pending(root, "20260501_outreach_alpha.md", "Pending Action: Alpha outreach")
    adapter = CareerCommandAdapter(root=root)

    for identifier in ["missing", "../20260501_outreach_alpha.md", ""]:
        try:
            adapter.approve_pending_action(identifier)
        except (FileNotFoundError, ValueError):
            pass
        else:
            raise AssertionError(f"Expected invalid pending id to fail: {identifier}")

    assert (root / "pending_actions" / "20260501_outreach_alpha.md").exists()
    assert not (root / "approved_actions" / "20260501_outreach_alpha.md").exists()


def test_no_external_send_apply_contact_commands_are_allowlisted(tmp_path: Path) -> None:
    root = _career_root(tmp_path)
    _write_tracker(root)
    _write_batch_summary(root)
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    adapter = CareerCommandAdapter(root=root, runner=runner)
    adapter.save_batch_rows_to_tracker("1")
    adapter.draft_outreach_for_tracker_rows("1")
    adapter.run_daily_scout_pipeline_preview()

    command_text = " ".join(" ".join(command[1:]) for command in calls)
    assert "send" not in command_text
    assert "apply" not in command_text
    assert "linkedin" not in command_text.lower()
    assert "browser" not in command_text
    assert "review_pending_actions" not in command_text


def _career_root(tmp_path: Path) -> Path:
    root = tmp_path / "career-command"
    for relative in [
        ".venv/bin",
        "data",
        "pending_actions",
        "approved_actions",
        "rejected_actions",
        "logs",
        "reports/scout_reports",
        "reports/job_evaluations",
        "tools",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    python = root / ".venv" / "bin" / "python"
    python.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    return root


def _write_tracker(root: Path) -> None:
    (root / "data" / "career_tracker.csv").write_text(
        "\n".join(
            [
                "company,role,location,overall_score,recommendation,status,next_action,source_url",
                "Alpha,Implementation Analyst,Remote,7.5,pursue,ready,tailor resume,https://a.test",
                "Beta,AI Analyst,Remote,8.3,network first,pending,find hiring manager,https://b.test",
                "Gamma,Operations Analyst,LA,6.9,save,watch,check later,https://c.test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_pending(root: Path, filename: str, title: str) -> None:
    _write_markdown(
        root / "pending_actions" / filename,
        "\n".join(
            [
                f"# {title}",
                "",
                "**Type:** outreach",
                "**Status:** pending",
                "",
                "Local draft only.",
            ]
        ),
    )


def _write_scout_report(root: Path) -> None:
    _write_markdown(
        root / "reports" / "scout_reports" / "latest.md",
        "\n".join(
            [
                "# Career Scout Report",
                "",
                "## Search Summary",
                "- Searched official implementation roles.",
                "- Found early-career AI operations fits.",
                "",
                "## Top Opportunities",
                "| Rank | Company | Role | Location | Source Type | Fit Score | "
                "Recommendation | Why |",
                "|---|---|---|---|---|---:|---|---|",
                "| 1 | Beta | AI Analyst | Remote | official | 8.3 | network first | strong fit |",
            ]
        ),
    )


def _write_batch_summary(root: Path) -> None:
    (root / "reports" / "job_evaluations" / "latest_batch_summary.csv").write_text(
        "\n".join(
            [
                "file,company,role,location,category,overall_score,recommendation,source_url,memo_path",
                "jobs_raw/a.txt,Corner,Junior Analyst,Remote,AI,7.6,pursue,https://c.test,memo-a.md",
                "jobs_raw/b.txt,Meridian,Implementation Analyst,Remote,Fintech,8.0,pursue,https://m.test,memo-b.md",
                "jobs_raw/c.txt,Parspec,Enablement Specialist,Remote,Construction,7.1,network first,https://p.test,memo-c.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def _read_action_log(root: Path) -> list[dict[str, str]]:
    with (root / "logs" / "action_log.csv").open(newline="", encoding="utf-8") as file:
        return [dict(row) for row in csv.DictReader(file)]
