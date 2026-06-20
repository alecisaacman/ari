from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TextIO
from uuid import UUID

from ari_core import approve_pending_approval, deny_pending_approval, list_pending_approvals
from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]


def _controller_outcome(result_run: object) -> str:
    trajectory = getattr(result_run, "controller_trajectory", None)
    if trajectory is None:
        return "none"
    return str(trajectory.controller_outcome)


def handle_list_pending_approvals(
    session_factory: SessionFactory,
    *,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        approvals = list_pending_approvals(session)
    if not approvals:
        stdout.write("No pending approvals.\n")
        return 0
    lines = ["pending_approvals"]
    for approval in approvals:
        lines.extend(
            [
                f"- id: {approval.id}",
                f"  run_id: {approval.run_id}",
                f"  requested_at: {approval.requested_at}",
                f"  decision: {approval.decision_summary}",
                f"  reason: {approval.reason}",
            ]
        )
    stdout.write("\n".join(lines) + "\n")
    return 0


def handle_approve_pending_approval(
    session_factory: SessionFactory,
    *,
    approval_id: UUID,
    approved_at: datetime | None,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = approve_pending_approval(session, approval_id=approval_id, approved_at=approved_at)
    if result is None:
        stdout.write(f"No pending approval found for {approval_id}.\n")
        return 1
    controller_outcome = _controller_outcome(result.run)
    stdout.write(
        "\n".join(
            [
                f"approved: {result.approval.id}",
                f"status: {result.approval.status}",
                f"run_id: {result.run.id}",
                f"controller_cycle_state: {result.run.controller_cycle_state}",
                f"controller_outcome: {controller_outcome}",
            ]
        )
        + "\n"
    )
    return 0


def handle_deny_pending_approval(
    session_factory: SessionFactory,
    *,
    approval_id: UUID,
    denied_at: datetime | None,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        result = deny_pending_approval(session, approval_id=approval_id, denied_at=denied_at)
    if result is None:
        stdout.write(f"No pending approval found for {approval_id}.\n")
        return 1
    controller_outcome = _controller_outcome(result.run)
    stdout.write(
        "\n".join(
            [
                f"denied: {result.approval.id}",
                f"status: {result.approval.status}",
                f"run_id: {result.run.id}",
                f"controller_cycle_state: {result.run.controller_cycle_state}",
                f"controller_outcome: {controller_outcome}",
            ]
        )
        + "\n"
    )
    return 0
