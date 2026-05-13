from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ari_career_command.adapter import (
    CareerBatchSummary,
    CareerCommandAdapter,
    CareerPendingActionsSummary,
    CareerScoutReportSummary,
    CareerStatus,
    CareerTrackerSummary,
)

CURRENT_OBJECTIVE = "Get Alec hired"
SAFETY_BOUNDARY = (
    "Local-only. No automatic applications, emails, LinkedIn messages, "
    "browser automation, or external contact."
)


@dataclass(frozen=True)
class CareerReportFile:
    path: Path
    kind: str
    updated_at: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "updated_at": self.updated_at,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class CareerCommandCenter:
    objective: str
    updated_at: str
    root: Path
    status: CareerStatus
    tracker: CareerTrackerSummary
    tracker_by_status: dict[str, int]
    pending: CareerPendingActionsSummary
    scout_report: CareerScoutReportSummary
    batch_summary: CareerBatchSummary
    latest_reports: list[CareerReportFile]
    recommended_next_actions: list[str]
    safety_boundary: str
    unavailable_reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "updated_at": self.updated_at,
            "root": str(self.root),
            "status": {
                "root_exists": self.status.root_exists,
                "python_exists": self.status.python_exists,
                "python_path": str(self.status.python_path),
                "tracker_count": self.status.tracker_count,
                "pending_count": self.status.pending_count,
                "approved_count": self.status.approved_count,
                "rejected_count": self.status.rejected_count,
                "latest_scout_report_exists": self.status.latest_scout_report_exists,
                "latest_batch_summary_exists": self.status.latest_batch_summary_exists,
            },
            "tracker": {
                "path": str(self.tracker.tracker_path),
                "exists": self.tracker.exists,
                "total_roles": self.tracker.total_count,
                "by_status": self.tracker_by_status,
                "top_roles": [
                    {
                        "company": item.company,
                        "role": item.role,
                        "location": item.location,
                        "overall_score": item.overall_score,
                        "recommendation": item.recommendation,
                        "status": item.status,
                        "next_action": item.next_action,
                        "source_url": item.source_url,
                    }
                    for item in self.tracker.opportunities
                ],
            },
            "pending_actions": [
                {
                    "id": Path(item.filename).stem,
                    "filename": item.filename,
                    "title": item.title,
                    "type": item.action_type,
                    "role": item.role,
                    "company": item.company,
                    "created_at": item.created_at,
                    "status": item.status,
                    "requires_approval": item.requires_approval,
                }
                for item in self.pending.drafts
            ],
            "reports": {
                "latest_scout": {
                    "path": str(self.scout_report.report_path),
                    "exists": self.scout_report.exists,
                    "title": self.scout_report.title,
                    "line_count": self.scout_report.line_count,
                    "search_summary": self.scout_report.search_summary,
                    "top_opportunities": self.scout_report.top_opportunities,
                },
                "latest_batch": {
                    "path": str(self.batch_summary.summary_path),
                    "exists": self.batch_summary.exists,
                    "total_count": self.batch_summary.total_count,
                    "opportunities": [
                        {
                            "company": item.company,
                            "role": item.role,
                            "location": item.location,
                            "overall_score": item.overall_score,
                            "recommendation": item.recommendation,
                            "source_url": item.source_url,
                            "memo_path": item.memo_path,
                        }
                        for item in self.batch_summary.opportunities
                    ],
                },
                "latest_files": [item.to_dict() for item in self.latest_reports],
            },
            "recommended_next_actions": self.recommended_next_actions,
            "safety_boundary": self.safety_boundary,
            "unavailable_reasons": self.unavailable_reasons,
        }


def build_career_command_center(
    adapter: CareerCommandAdapter | None = None,
    *,
    tracker_limit: int = 8,
    pending_limit: int = 12,
    report_limit: int = 8,
) -> CareerCommandCenter:
    adapter = adapter or CareerCommandAdapter()
    status = adapter.career_status()
    full_tracker = adapter.career_tracker_summary(limit=10_000)
    tracker = adapter.career_tracker_summary(limit=tracker_limit)
    pending = adapter.career_pending_actions_summary(limit=pending_limit)
    scout_report = adapter.career_latest_scout_report_summary()
    batch_summary = adapter.career_latest_batch_summary(limit=tracker_limit)
    latest_reports = _latest_report_files(adapter.root, limit=report_limit)
    unavailable_reasons = _unavailable_reasons(status, tracker, pending)
    return CareerCommandCenter(
        objective=CURRENT_OBJECTIVE,
        updated_at=datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        root=adapter.root,
        status=status,
        tracker=tracker,
        tracker_by_status=_tracker_by_status(full_tracker),
        pending=pending,
        scout_report=scout_report,
        batch_summary=batch_summary,
        latest_reports=latest_reports,
        recommended_next_actions=_recommended_next_actions(
            status=status,
            tracker=tracker,
            pending=pending,
            batch_summary=batch_summary,
            scout_report=scout_report,
        ),
        safety_boundary=SAFETY_BOUNDARY,
        unavailable_reasons=unavailable_reasons,
    )


def _tracker_by_status(summary: CareerTrackerSummary) -> dict[str, int]:
    counts = Counter(_normalize_status(item.status) for item in summary.opportunities)
    return dict(sorted(counts.items()))


def _normalize_status(status: str) -> str:
    normalized = "_".join(status.strip().lower().split())
    return normalized or "unknown"


def _latest_report_files(root: Path, *, limit: int) -> list[CareerReportFile]:
    reports_root = root / "reports"
    if not reports_root.exists():
        return []
    candidates = [
        path
        for path in reports_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".csv", ".txt"}
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        CareerReportFile(
            path=path,
            kind=_report_kind(path),
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            .replace(microsecond=0)
            .isoformat(),
            size_bytes=path.stat().st_size,
        )
        for path in candidates[:limit]
    ]


def _report_kind(path: Path) -> str:
    parts = set(path.parts)
    if "scout_reports" in parts:
        return "scout_report"
    if "job_evaluations" in parts:
        return "job_evaluation"
    return "report"


def _recommended_next_actions(
    *,
    status: CareerStatus,
    tracker: CareerTrackerSummary,
    pending: CareerPendingActionsSummary,
    batch_summary: CareerBatchSummary,
    scout_report: CareerScoutReportSummary,
) -> list[str]:
    actions: list[str] = []
    if pending.total_count:
        actions.append(f"Review {pending.total_count} pending local action draft(s).")
    if batch_summary.exists and batch_summary.total_count:
        actions.append(
            f"Review latest batch summary and save the best of {batch_summary.total_count} "
            "evaluated role(s)."
        )
    if tracker.total_count:
        follow_up_count = sum(
            1
            for item in tracker.opportunities
            if "follow" in item.status.lower() or "follow" in item.next_action.lower()
        )
        if follow_up_count:
            actions.append(f"Follow up on {follow_up_count} tracked role(s) flagged for follow-up.")
        else:
            actions.append(
                "Pick the highest-score tracked role and decide resume/outreach next step."
            )
    if not scout_report.exists:
        actions.append("Run scout preview when ready to refresh the opportunity queue.")
    if not status.root_exists:
        actions.append("Set CAREER_COMMAND_ROOT to the existing Career Command prototype path.")
    if not actions:
        actions.append(
            "Run scout preview for AI implementation roles in construction, finance, and SaaS."
        )
    actions.append(
        "Keep every external-facing action in local draft state until explicit approval."
    )
    return actions


def _unavailable_reasons(
    status: CareerStatus,
    tracker: CareerTrackerSummary,
    pending: CareerPendingActionsSummary,
) -> list[str]:
    reasons: list[str] = []
    if not status.root_exists:
        reasons.append(f"Career Command root is missing: {status.root}")
    if not tracker.exists:
        reasons.append(f"Tracker CSV is missing: {tracker.tracker_path}")
    if not pending.exists:
        reasons.append(f"Pending actions folder is missing: {pending.pending_dir}")
    if not status.latest_scout_report_exists:
        reasons.append("Latest scout report is missing.")
    if not status.latest_batch_summary_exists:
        reasons.append("Latest batch evaluation summary is missing.")
    return reasons
