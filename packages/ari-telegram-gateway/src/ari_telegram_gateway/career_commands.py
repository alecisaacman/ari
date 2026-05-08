from __future__ import annotations

from typing import Protocol

from ari_career_command import (
    CareerBatchSummary,
    CareerCommandAdapter,
    CareerCommandResult,
    CareerDashboardInfo,
    CareerPendingActionReview,
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

    def save_batch_rows_to_tracker(self, rows: str) -> CareerCommandResult: ...

    def draft_outreach_for_tracker_rows(self, rows: str) -> CareerCommandResult: ...

    def approve_pending_action(self, pending_id_or_filename: str) -> CareerPendingActionReview: ...

    def reject_pending_action(self, pending_id_or_filename: str) -> CareerPendingActionReview: ...

    def run_daily_scout_pipeline_preview(self) -> list[CareerCommandResult]: ...


def handle_career_command(
    raw_text: str,
    *,
    adapter: CareerCommandAdapterProtocol | None = None,
) -> str | None:
    parts = raw_text.strip().split()
    if not parts or parts[0].lower() != "/career":
        return None

    command = parts[1].lower() if len(parts) > 1 else "help"
    args = parts[2:]
    adapter = adapter or CareerCommandAdapter()

    try:
        if command == "help":
            return _format_help()
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
        if command == "save":
            if not args:
                return "Usage: /career save <rows>, for example /career save 1,3 or 1-3"
            return _format_command_result(
                "Career save",
                adapter.save_batch_rows_to_tracker(" ".join(args)),
                "Saved selected batch rows to the local tracker only.",
            )
        if command == "draft":
            if not args:
                return "Usage: /career draft <rows>, for example /career draft 1,3 or 1-3"
            return _format_command_result(
                "Career draft",
                adapter.draft_outreach_for_tracker_rows(" ".join(args)),
                "Created local pending outreach drafts only.",
            )
        if command == "approve":
            if not args:
                return "Usage: /career approve <pending_id_or_filename>"
            return _format_review_result(adapter.approve_pending_action(args[0]))
        if command == "reject":
            if not args:
                return "Usage: /career reject <pending_id_or_filename>"
            return _format_review_result(adapter.reject_pending_action(args[0]))
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


def _format_command_result(title: str, result: CareerCommandResult, success_line: str) -> str:
    status = "ok" if result.ok else f"failed ({result.returncode})"
    lines = [f"{title}: {status}"]
    if result.ok:
        lines.append(success_line)
    detail = _concise_command_output(result.stdout if result.stdout else result.stderr)
    lines.extend(detail)
    lines.append(
        "Safety: no applications, emails, LinkedIn messages, or external contact were sent."
    )
    return "\n".join(lines)


def _format_review_result(result: CareerPendingActionReview) -> str:
    verb = "Approved" if result.status == "approved" else "Rejected"
    return "\n".join(
        [
            f"{verb} local pending action.",
            f"Action: {result.title}",
            f"File: {result.destination_path.name}",
            "Safety: this updated local approval state only. Nothing was sent externally.",
        ]
    )


def _format_help() -> str:
    return "\n".join(
        [
            "Career Command commands:",
            "/career help",
            "/career status",
            "/career tracker",
            "/career pending",
            "/career latest",
            "/career dashboard",
            "/career scout_preview",
            "/career save <rows>",
            "/career draft <rows>",
            "/career approve <pending_id_or_filename>",
            "/career reject <pending_id_or_filename>",
            "Safety: local-only. No applications, emails, LinkedIn messages, "
            "browser automation, or external contact.",
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


def _concise_command_output(value: str) -> list[str]:
    interesting_prefixes = (
        "Saved ",
        "Created:",
        "Created pending actions:",
        "No new rows",
        "Skipped:",
        "Batch outreach complete.",
        "- Row ",
        "- ",
    )
    lines: list[str] = []
    for line in value.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith(interesting_prefixes):
            lines.append(text)
        if len(lines) >= 8:
            break
    if lines:
        return lines
    first = _first_nonempty_line(value)
    return [first] if first else []
