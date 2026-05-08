from __future__ import annotations

import csv
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CAREER_COMMAND_ROOT = "~/code/openai-dev-sandbox"
DEFAULT_DASHBOARD_URL = "http://localhost:8501"
COMMAND_TIMEOUT_SECONDS = 1_200

CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class TrackedOpportunity:
    company: str
    role: str
    location: str
    overall_score: float
    recommendation: str
    status: str
    next_action: str
    source_url: str


@dataclass(frozen=True)
class PendingActionDraft:
    filename: str
    title: str
    action_type: str
    status: str


@dataclass(frozen=True)
class BatchOpportunity:
    file: str
    company: str
    role: str
    location: str
    overall_score: float
    recommendation: str
    source_url: str
    memo_path: str


@dataclass(frozen=True)
class CareerStatus:
    root: Path
    root_exists: bool
    python_path: Path
    python_exists: bool
    tracker_count: int
    pending_count: int
    approved_count: int
    rejected_count: int
    latest_scout_report_exists: bool
    latest_batch_summary_exists: bool


@dataclass(frozen=True)
class CareerTrackerSummary:
    tracker_path: Path
    exists: bool
    total_count: int
    opportunities: list[TrackedOpportunity]


@dataclass(frozen=True)
class CareerPendingActionsSummary:
    pending_dir: Path
    exists: bool
    total_count: int
    drafts: list[PendingActionDraft]


@dataclass(frozen=True)
class CareerScoutReportSummary:
    report_path: Path
    exists: bool
    title: str
    search_summary: list[str]
    top_opportunities: list[str]
    line_count: int


@dataclass(frozen=True)
class CareerBatchSummary:
    summary_path: Path
    exists: bool
    total_count: int
    opportunities: list[BatchOpportunity]


@dataclass(frozen=True)
class CareerDashboardInfo:
    dashboard_path: Path
    exists: bool
    local_url: str
    run_command: str


@dataclass(frozen=True)
class CareerCommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CareerCommandAdapter:
    """Thin adapter over the existing local Career Command sandbox."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        configured_root = root or Path(
            os.environ.get("CAREER_COMMAND_ROOT", DEFAULT_CAREER_COMMAND_ROOT)
        )
        self.root = configured_root.expanduser()
        self.python_path = self.root / ".venv" / "bin" / "python"
        self._runner = runner or _subprocess_runner

    def career_status(self) -> CareerStatus:
        return CareerStatus(
            root=self.root,
            root_exists=self.root.exists(),
            python_path=self.python_path,
            python_exists=self.python_path.exists(),
            tracker_count=len(_read_csv_rows(self._tracker_path())),
            pending_count=_count_markdown_files(self.root / "pending_actions"),
            approved_count=_count_markdown_files(self.root / "approved_actions"),
            rejected_count=_count_markdown_files(self.root / "rejected_actions"),
            latest_scout_report_exists=self._latest_scout_report_path().exists(),
            latest_batch_summary_exists=self._latest_batch_summary_path().exists(),
        )

    def career_tracker_summary(self, *, limit: int = 5) -> CareerTrackerSummary:
        path = self._tracker_path()
        opportunities = [
            TrackedOpportunity(
                company=_cell(row, "company"),
                role=_cell(row, "role"),
                location=_cell(row, "location"),
                overall_score=_score(_cell(row, "overall_score")),
                recommendation=_cell(row, "recommendation"),
                status=_cell(row, "status"),
                next_action=_cell(row, "next_action"),
                source_url=_cell(row, "source_url"),
            )
            for row in _read_csv_rows(path)
        ]
        opportunities.sort(key=lambda item: item.overall_score, reverse=True)
        return CareerTrackerSummary(
            tracker_path=path,
            exists=path.exists(),
            total_count=len(opportunities),
            opportunities=opportunities[:limit],
        )

    def career_pending_actions_summary(self, *, limit: int = 10) -> CareerPendingActionsSummary:
        pending_dir = self.root / "pending_actions"
        files = _markdown_files(pending_dir)
        drafts = [
            PendingActionDraft(
                filename=path.name,
                title=_pending_title(path),
                action_type=_markdown_field(path, "Type"),
                status=_markdown_field(path, "Status"),
            )
            for path in files[:limit]
        ]
        return CareerPendingActionsSummary(
            pending_dir=pending_dir,
            exists=pending_dir.exists(),
            total_count=len(files),
            drafts=drafts,
        )

    def career_latest_scout_report_summary(self) -> CareerScoutReportSummary:
        path = self._latest_scout_report_path()
        if not path.exists():
            return CareerScoutReportSummary(
                report_path=path,
                exists=False,
                title="",
                search_summary=[],
                top_opportunities=[],
                line_count=0,
            )
        lines = path.read_text(encoding="utf-8").splitlines()
        return CareerScoutReportSummary(
            report_path=path,
            exists=True,
            title=_first_heading(lines),
            search_summary=_bullets_after_heading(lines, "## Search Summary", limit=5),
            top_opportunities=_table_rows_after_heading(lines, "## Top Opportunities", limit=5),
            line_count=len(lines),
        )

    def career_latest_batch_summary(self, *, limit: int = 5) -> CareerBatchSummary:
        path = self._latest_batch_summary_path()
        opportunities = [
            BatchOpportunity(
                file=_cell(row, "file"),
                company=_cell(row, "company"),
                role=_cell(row, "role"),
                location=_cell(row, "location"),
                overall_score=_score(_cell(row, "overall_score")),
                recommendation=_cell(row, "recommendation"),
                source_url=_cell(row, "source_url"),
                memo_path=_cell(row, "memo_path"),
            )
            for row in _read_csv_rows(path)
        ]
        opportunities.sort(key=lambda item: item.overall_score, reverse=True)
        return CareerBatchSummary(
            summary_path=path,
            exists=path.exists(),
            total_count=len(opportunities),
            opportunities=opportunities[:limit],
        )

    def career_dashboard_info(self) -> CareerDashboardInfo:
        dashboard_path = self.root / "ace_career_dashboard.py"
        return CareerDashboardInfo(
            dashboard_path=dashboard_path,
            exists=dashboard_path.exists(),
            local_url=DEFAULT_DASHBOARD_URL,
            run_command=(
                f"cd {self.root} && {self.python_path} -m streamlit run "
                "ace_career_dashboard.py"
            ),
        )

    def run_career_scout(self) -> CareerCommandResult:
        return self._run_known_script(["career_scout.py"])

    def extract_jobs_from_latest_scout(self) -> CareerCommandResult:
        return self._run_known_script(["tools/scout_report_to_jobs.py"])

    def batch_evaluate_jobs(self, *, limit: int = 5) -> CareerCommandResult:
        return self._run_known_script(["tools/batch_evaluate_jobs.py", "--limit", str(limit)])

    def run_daily_scout_pipeline_preview(self) -> list[CareerCommandResult]:
        results: list[CareerCommandResult] = []
        for command in (
            self.run_career_scout,
            self.extract_jobs_from_latest_scout,
            lambda: self.batch_evaluate_jobs(limit=5),
        ):
            result = command()
            results.append(result)
            if not result.ok:
                break
        return results

    def _run_known_script(self, script_args: list[str]) -> CareerCommandResult:
        self._validate_script_args(script_args)
        command = [str(self.python_path), *script_args]
        completed = self._runner(command, self.root)
        return CareerCommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def _validate_script_args(self, script_args: list[str]) -> None:
        allowed = {
            ("career_scout.py",),
            ("tools/scout_report_to_jobs.py",),
            ("tools/batch_evaluate_jobs.py", "--limit", "5"),
        }
        if tuple(script_args) not in allowed:
            raise ValueError(f"Career Command script is not allowlisted: {script_args!r}")
        if not self.root.exists():
            raise FileNotFoundError(f"Career Command root does not exist: {self.root}")
        if not self.python_path.exists():
            raise FileNotFoundError(
                f"Career Command venv Python does not exist: {self.python_path}"
            )

    def _tracker_path(self) -> Path:
        return self.root / "data" / "career_tracker.csv"

    def _latest_scout_report_path(self) -> Path:
        return self.root / "reports" / "scout_reports" / "latest.md"

    def _latest_batch_summary_path(self) -> Path:
        return self.root / "reports" / "job_evaluations" / "latest_batch_summary.csv"


def _subprocess_runner(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def _cell(row: dict[str, str], key: str) -> str:
    return str(row.get(key) or "").strip()


def _score(value: str) -> float:
    text = value.replace("/10", "").strip()
    if not text:
        return 0.0
    try:
        return float(text.split()[0])
    except ValueError:
        return 0.0


def _count_markdown_files(path: Path) -> int:
    return len(_markdown_files(path))


def _markdown_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)


def _pending_title(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        text = line.strip()
        if text.startswith("# "):
            return text[2:].strip()
    return path.stem


def _markdown_field(path: Path, field: str) -> str:
    marker = f"**{field}:**"
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith(marker):
            return text.removeprefix(marker).strip()
    return ""


def _first_heading(lines: list[str]) -> str:
    for line in lines:
        text = line.strip()
        if text.startswith("# "):
            return text[2:].strip()
    return ""


def _bullets_after_heading(lines: list[str], heading: str, *, limit: int) -> list[str]:
    items: list[str] = []
    inside = False
    for line in lines:
        text = line.strip()
        if text == heading:
            inside = True
            continue
        if inside and text.startswith("## "):
            break
        if inside and text.startswith("- "):
            items.append(text[2:].strip())
            if len(items) >= limit:
                break
    return items


def _table_rows_after_heading(lines: list[str], heading: str, *, limit: int) -> list[str]:
    rows: list[str] = []
    inside = False
    for line in lines:
        text = line.strip()
        if text == heading:
            inside = True
            continue
        if inside and text.startswith("## "):
            break
        if not inside or not text.startswith("|"):
            continue
        if "---" in text or "Rank" in text:
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if len(cells) >= 7:
            rows.append(f"{cells[0]}. {cells[1]} - {cells[2]} ({cells[5]}, {cells[6]})")
            if len(rows) >= limit:
                break
    return rows
