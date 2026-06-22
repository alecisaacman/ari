from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ari_career_command import CareerCommandAdapter, build_career_command_center
from ari_career_command.read_model import SAFETY_BOUNDARY, CareerCommandCenter

from ari_core.surface_status import SurfaceState, SurfaceStatusStore, build_surface_status


def handle_career_status(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="status", render=_render_status)


def handle_career_tracker(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="tracker", render=_render_tracker)


def handle_career_pending(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="pending", render=_render_pending)


def handle_career_reports(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="reports", render=_render_reports)


def handle_career_next(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="next", render=_render_next)


def handle_career_command_center(args: argparse.Namespace) -> int:
    return _handle_read_command(args, command="command-center", render=_render_command_center)


def handle_career_scout_preview(args: argparse.Namespace) -> int:
    adapter = _adapter_from_args(args)
    _write_career_status(
        args,
        state=SurfaceState.ROUTING,
        summary="Career Command scout preview requested.",
        command="scout-preview",
    )
    _write_career_status(
        args,
        state=SurfaceState.WORKING,
        summary="Career Command is running safe scout preview scripts.",
        command="scout-preview",
    )
    try:
        results = adapter.run_daily_scout_pipeline_preview()
        center = build_career_command_center(adapter)
    except Exception as exc:
        _write_career_status(
            args,
            state=SurfaceState.ERROR,
            summary=f"Career Command scout preview failed: {exc}",
            command="scout-preview",
        )
        return _print_error(args, f"Career Command scout preview failed: {exc}")

    ok = all(result.ok for result in results)
    payload = {
        "command": "scout-preview",
        "ok": ok,
        "results": [
            {
                "command": result.command[1:],
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            for result in results
        ],
        "latest_batch": center.to_dict()["reports"]["latest_batch"],
        "safety_boundary": SAFETY_BOUNDARY,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("CAREER SCOUT PREVIEW")
        print("- Ran only scout, extraction, and batch evaluation preview commands.")
        for result in results:
            status = "ok" if result.ok else f"failed ({result.returncode})"
            print(f"- {' '.join(result.command[1:])}: {status}")
            if not result.ok:
                detail = _first_nonempty_line(result.stderr) or _first_nonempty_line(result.stdout)
                if detail:
                    print(f"  Detail: {detail}")
                break
        print(f"- Safety: {SAFETY_BOUNDARY}")
    _write_career_status(
        args,
        state=SurfaceState.SUCCESS if ok else SurfaceState.ERROR,
        summary=(
            "Career Command scout preview completed."
            if ok
            else "Career Command scout preview failed; no external action was taken."
        ),
        command="scout-preview",
        metadata={"ok": ok},
    )
    return 0 if ok else 1


def _handle_read_command(
    args: argparse.Namespace,
    *,
    command: str,
    render,
) -> int:
    adapter = _adapter_from_args(args)
    _write_career_status(
        args,
        state=SurfaceState.ROUTING,
        summary=f"Career Command {command} requested.",
        command=command,
    )
    _write_career_status(
        args,
        state=SurfaceState.WORKING,
        summary="Career Command is reading tracker, reports, and pending actions.",
        command=command,
    )
    try:
        center = build_career_command_center(adapter)
    except Exception as exc:
        _write_career_status(
            args,
            state=SurfaceState.ERROR,
            summary=f"Career Command {command} failed: {exc}",
            command=command,
        )
        return _print_error(args, f"Career Command {command} failed: {exc}")

    render(args, center)
    final_state = (
        SurfaceState.WAITING_FOR_APPROVAL
        if center.pending.total_count and command in {"command-center", "pending", "next"}
        else SurfaceState.SUCCESS
    )
    final_summary = (
        f"{center.pending.total_count} Career Command draft(s) need review."
        if final_state == SurfaceState.WAITING_FOR_APPROVAL
        else f"Career Command {command} updated."
    )
    _write_career_status(
        args,
        state=final_state,
        summary=final_summary,
        command=command,
        metadata={
            "pending_count": center.pending.total_count,
            "tracker_count": center.tracker.total_count,
        },
    )
    return 0


def _adapter_from_args(args: argparse.Namespace) -> CareerCommandAdapter:
    root = Path(args.root).expanduser() if args.root else None
    return CareerCommandAdapter(root=root)


def _render_command_center(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    if args.as_json:
        print(json.dumps(center.to_dict(), indent=2, sort_keys=True))
        return
    _print_header(center)
    _print_tracker(center)
    _print_pending(center)
    _print_reports(center)
    _print_next(center)
    print(f"- Safety: {center.safety_boundary}")
    print(f"- Last updated: {center.updated_at}")


def _render_status(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    if args.as_json:
        print(json.dumps(center.to_dict()["status"], indent=2, sort_keys=True))
        return
    status = center.status
    print("CAREER COMMAND STATUS")
    print(f"- Root: {_yes_no(status.root_exists)} {status.root}")
    print(f"- Sandbox Python: {_yes_no(status.python_exists)} {status.python_path}")
    print(f"- Tracked roles: {status.tracker_count}")
    print(f"- Pending approvals: {status.pending_count}")
    print(f"- Approved local actions: {status.approved_count}")
    print(f"- Rejected local actions: {status.rejected_count}")
    print(f"- Latest scout report: {_yes_no(status.latest_scout_report_exists)}")
    print(f"- Latest batch summary: {_yes_no(status.latest_batch_summary_exists)}")
    print(f"- Safety: {center.safety_boundary}")


def _render_tracker(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    payload = center.to_dict()["tracker"]
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    _print_tracker(center)


def _render_pending(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    payload = {"pending_actions": center.to_dict()["pending_actions"]}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    _print_pending(center)


def _render_reports(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    payload = center.to_dict()["reports"]
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    _print_reports(center)


def _render_next(args: argparse.Namespace, center: CareerCommandCenter) -> None:
    payload = {"recommended_next_actions": center.recommended_next_actions}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    _print_next(center)


def _print_header(center: CareerCommandCenter) -> None:
    print("CAREER COMMAND CENTER")
    print(f"- Current objective: {center.objective}")
    print(f"- Prototype root: {center.root}")
    if center.unavailable_reasons:
        print("- Unavailable inputs:")
        for reason in center.unavailable_reasons:
            print(f"  - {reason}")


def _print_tracker(center: CareerCommandCenter) -> None:
    print("TRACKER")
    print(f"- Total roles: {center.tracker.total_count}")
    if center.tracker_by_status:
        by_status = ", ".join(
            f"{status}: {count}" for status, count in center.tracker_by_status.items()
        )
        print(f"- By status: {by_status}")
    if not center.tracker.exists:
        print(f"- Missing tracker: {center.tracker.tracker_path}")
        return
    for item in center.tracker.opportunities[:5]:
        print(
            f"- {item.company} | {item.role} | score {item.overall_score:g} | "
            f"{item.recommendation} | {item.status}"
        )
        if item.next_action:
            print(f"  Next: {item.next_action}")


def _print_pending(center: CareerCommandCenter) -> None:
    print("PENDING APPROVALS")
    if not center.pending.exists:
        print(f"- Missing pending folder: {center.pending.pending_dir}")
        return
    if not center.pending.total_count:
        print("- None")
        return
    print(f"- Total pending drafts: {center.pending.total_count}")
    for draft in center.pending.drafts[:8]:
        label = draft.title or draft.filename
        descriptor = " / ".join(part for part in [draft.company, draft.role] if part)
        suffix = f" - {descriptor}" if descriptor else ""
        print(f"- {label}{suffix}")
        print(f"  File: {draft.filename}")


def _print_reports(center: CareerCommandCenter) -> None:
    print("REPORTS")
    scout = center.scout_report
    batch = center.batch_summary
    print(f"- Latest scout: {_yes_no(scout.exists)} {scout.report_path}")
    if scout.exists and scout.title:
        print(f"  Title: {scout.title}")
    print(f"- Latest batch summary: {_yes_no(batch.exists)} {batch.summary_path}")
    if batch.exists:
        print(f"  Evaluated roles: {batch.total_count}")
    if center.latest_reports:
        print("- Recent report files:")
        for report in center.latest_reports[:5]:
            print(f"  - {report.kind}: {report.path}")


def _print_next(center: CareerCommandCenter) -> None:
    print("RECOMMENDED NEXT ACTIONS")
    for action in center.recommended_next_actions:
        print(f"- {action}")


def _write_career_status(
    args: argparse.Namespace,
    *,
    state: SurfaceState,
    summary: str,
    command: str,
    metadata: dict[str, object] | None = None,
) -> None:
    status = build_surface_status(
        state=state,
        summary=summary,
        source="career_command",
        metadata={
            "module": "career_command",
            "surface": "local_cli",
            "command": command,
            **(metadata or {}),
        },
    )
    SurfaceStatusStore(root_dir=args.status_dir).write(status)


def _print_error(args: argparse.Namespace, message: str) -> int:
    if args.as_json:
        print(json.dumps({"error": message}, indent=2, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return 1


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _first_nonempty_line(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text:
            return text
    return ""
