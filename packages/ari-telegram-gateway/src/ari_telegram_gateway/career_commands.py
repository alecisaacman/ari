from __future__ import annotations

from typing import Protocol

from ari_career_command import (
    CareerBatchSummary,
    CareerCommandAdapter,
    CareerCommandResult,
    CareerDashboardInfo,
    CareerPendingActionsSummary,
    CareerScoutReportSummary,
    CareerStatus,
    CareerTrackerSummary,
)


class CareerCommandAdapterProtocol(Protocol):
    def career_status(self) -> CareerStatus: ...

    def career_tracker_summary(self, *, limit: int = 5) -> CareerTrackerSummary: ...

    def career_pending_actions_summary(self, *, limit: int = 10) -> CareerPendingActionsSummary: ...

    def career_latest_scout_report_summary(self) -> CareerScoutReportSummary: ...

    def career_latest_batch_summary(self, *, limit: int = 5) -> CareerBatchSummary: ...

    def career_dashboard_info(self) -> CareerDashboardInfo: ...

    def run_daily_scout_pipeline_preview(self) -> list[CareerCommandResult]: ...


def handle_career_command(
    raw_text: str,
    *,
    adapter: CareerCommandAdapterProtocol | None = None,
) -> str | None:
    parts = raw_text.strip().split()
    if not parts or parts[0].lower() != "/career":
        return None

    command = parts[1].lower() if len(parts) > 1 else "status"
    adapter = adapter or CareerCommandAdapter()

    try:
        if command == "status":
            return _format_status(adapter.career_status())
        if command == "tracker":
            return _format_tracker(adapter.career_tracker_summary(limit=5))
        if command == "pending":
            return _format_pending(adapter.career_pending_actions_summary(limit=10))
        if command == "latest":
            return _format_latest(
                adapter.career_latest_scout_report_summary(),
                adapter.career_latest_batch_summary(limit=5),
            )
        if command == "dashboard":
            return _format_dashboard(adapter.career_dashboard_info())
        if command == "scout_preview":
            return _format_scout_preview(adapter)
    except Exception as exc:
        return f"Career Command error: {exc}"

    return _format_help()


def _format_status(status: CareerStatus) -> str:
    return "\n".join(
        [
            "Career Command status",
            f"Root: {_yes_no(status.root_exists)} {status.root}",
            f"Sandbox Python: {_yes_no(status.python_exists)} {status.python_path}",
            f"Tracked opportunities: {status.tracker_count}",
            f"Pending actions: {status.pending_count}",
            f"Approved actions: {status.approved_count}",
            f"Rejected actions: {status.rejected_count}",
            f"Latest scout report: {_yes_no(status.latest_scout_report_exists)}",
            f"Latest batch summary: {_yes_no(status.latest_batch_summary_exists)}",
            "Safety: no applications, emails, LinkedIn messages, or external contact are sent.",
        ]
    )


def _format_tracker(summary: CareerTrackerSummary) -> str:
    if not summary.exists:
        return f"Career tracker not found: {summary.tracker_path}"
    if not summary.opportunities:
        return "Career tracker exists, but no tracked opportunities were found."
    lines = [f"Top tracked opportunities ({summary.total_count} total)"]
    for index, item in enumerate(summary.opportunities, start=1):
        lines.append(
            f"{index}. {item.company} - {item.role} | "
            f"{item.overall_score:g} | {item.recommendation} | {item.status}"
        )
        if item.next_action:
            lines.append(f"   Next: {item.next_action}")
    return "\n".join(lines)


def _format_pending(summary: CareerPendingActionsSummary) -> str:
    if not summary.exists:
        return f"Pending actions folder not found: {summary.pending_dir}"
    if not summary.drafts:
        return "No pending Career Command action drafts."
    lines = [f"Pending Career Command drafts ({summary.total_count} total)"]
    for index, draft in enumerate(summary.drafts, start=1):
        label = draft.title or draft.filename
        metadata = " / ".join(part for part in [draft.action_type, draft.status] if part)
        suffix = f" ({metadata})" if metadata else ""
        lines.append(f"{index}. {label}{suffix}")
        lines.append(f"   File: {draft.filename}")
    lines.append("Safety: drafts remain local until explicit human approval.")
    return "\n".join(lines)


def _format_latest(scout: CareerScoutReportSummary, batch: CareerBatchSummary) -> str:
    lines = ["Latest Career Command output"]
    if scout.exists:
        scout_title = scout.title or scout.report_path.name
        lines.append(f"Scout report: {scout_title} ({scout.line_count} lines)")
        for bullet in scout.search_summary[:3]:
            lines.append(f"- {bullet}")
        for opportunity in scout.top_opportunities[:3]:
            lines.append(f"- {opportunity}")
    else:
        lines.append(f"Scout report: missing at {scout.report_path}")

    if batch.exists:
        lines.append(f"Batch summary: {batch.total_count} evaluated opportunities")
        for index, item in enumerate(batch.opportunities, start=1):
            lines.append(
                f"{index}. {item.company} - {item.role} | "
                f"{item.overall_score:g} | {item.recommendation}"
            )
    else:
        lines.append(f"Batch summary: missing at {batch.summary_path}")
    return "\n".join(lines)


def _format_dashboard(info: CareerDashboardInfo) -> str:
    return "\n".join(
        [
            "Career Command dashboard",
            f"Dashboard file: {_yes_no(info.exists)} {info.dashboard_path}",
            f"Local URL: {info.local_url}",
            f"Run command: {info.run_command}",
        ]
    )


def _format_scout_preview(adapter: CareerCommandAdapterProtocol) -> str:
    results = adapter.run_daily_scout_pipeline_preview()
    lines = [
        "Career scout preview finished.",
        "Ran only: scout -> extract jobs -> batch evaluate --limit 5.",
    ]
    for result in results:
        script = " ".join(result.command[1:])
        status = "ok" if result.ok else f"failed ({result.returncode})"
        lines.append(f"- {script}: {status}")
        if not result.ok:
            detail = _first_nonempty_line(result.stderr) or _first_nonempty_line(result.stdout)
            if detail:
                lines.append(f"  Detail: {detail}")
            break

    batch = adapter.career_latest_batch_summary(limit=5)
    if batch.exists:
        lines.append(f"Latest batch summary: {batch.total_count} evaluated opportunities")
        for index, item in enumerate(batch.opportunities, start=1):
            lines.append(
                f"{index}. {item.company} - {item.role} | "
                f"{item.overall_score:g} | {item.recommendation}"
            )
    lines.append(
        "Stopped for review. No jobs saved, drafts created, approvals made, or messages sent."
    )
    return "\n".join(lines)


def _format_help() -> str:
    return "\n".join(
        [
            "Career Command commands:",
            "/career status",
            "/career tracker",
            "/career pending",
            "/career latest",
            "/career dashboard",
            "/career scout_preview",
        ]
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _first_nonempty_line(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text:
            return text
    return ""
