from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import TextIO
from uuid import UUID

from ari_core import (
    OrchestrationRunComparison,
    OrchestrationRunDetails,
    RunSignalOrchestrationInput,
    compare_latest_two_runs,
    get_latest_run_details,
    get_previous_run_details,
    run_signal_orchestration,
)
from ari_state import Alert, ControllerEvent, Signal
from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]


def handle_run_orchestration(
    session_factory: SessionFactory,
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    detected_at = datetime.now(tz=UTC)
    orchestration_input = RunSignalOrchestrationInput(
        state_date=state_date,
        detected_at=detected_at,
    )
    with session_factory() as session:
        result = run_signal_orchestration(session, orchestration_input)
    run = result.run
    stdout.write(f"orchestration run complete for {run.state_date.isoformat()}\n")
    stdout.write(f"run_id: {run.id}\n")
    stdout.write(f"executed_at: {_format_datetime(run.executed_at)}\n")
    stdout.write(f"state_fingerprint: {run.state_fingerprint}\n")
    stdout.write(f"signals: {len(result.signals)}\n")
    stdout.write(f"alerts: {len(result.alerts)}\n")
    if result.signals:
        stdout.write("\nsignals\n")
        stdout.write(_render_signal_block(result.signals))
        stdout.write("\n")
    if result.alerts:
        stdout.write("\nalerts\n")
        stdout.write(_render_alert_block(result.alerts))
        stdout.write("\n")
    return 0


def handle_latest_run(
    session_factory: SessionFactory,
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        details = get_latest_run_details(session, state_date=state_date)
    if details is None:
        stdout.write(f"No orchestration run found for {state_date.isoformat()}.\n")
        return 1
    stdout.write(render_run_details("latest", details))
    return 0


def handle_previous_run(
    session_factory: SessionFactory,
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        details = get_previous_run_details(session, state_date=state_date)
    if details is None:
        stdout.write(f"No previous orchestration run found for {state_date.isoformat()}.\n")
        return 1
    stdout.write(render_run_details("previous", details))
    return 0


def handle_compare_latest_two_runs(
    session_factory: SessionFactory,
    *,
    state_date: date,
    stdout: TextIO,
) -> int:
    with session_factory() as session:
        comparison = compare_latest_two_runs(session, state_date=state_date)
        latest = get_latest_run_details(session, state_date=state_date)
        previous = get_previous_run_details(session, state_date=state_date)
    if comparison is None or latest is None or previous is None:
        stdout.write(
            "Need at least two orchestration runs to compare "
            f"for {state_date.isoformat()}.\n"
        )
        return 1
    stdout.write(render_run_comparison(comparison, latest, previous))
    return 0


def render_run_details(label: str, details: OrchestrationRunDetails) -> str:
    run = details.run
    sections = [
        f"{label} orchestration run for {run.state_date.isoformat()}",
        f"run_id: {run.id}",
        f"executed_at: {_format_datetime(run.executed_at)}",
        f"state_fingerprint: {run.state_fingerprint}",
        f"signals: {len(details.signals)}",
        f"alerts: {len(details.alerts)}",
        f"controller_cycle_state: {run.controller_cycle_state or 'none'}",
        (
            "pending_approval: "
            f"{details.pending_approval.id if details.pending_approval is not None else 'none'}"
        ),
        _render_controller_summary(run),
        "",
        "signals",
        _render_signal_block(details.signals),
        "",
        "alerts",
        _render_alert_block(details.alerts),
        "",
        "controller_events",
        _render_controller_event_block(details.controller_events),
        "",
    ]
    return "\n".join(sections)


def render_run_comparison(
    comparison: OrchestrationRunComparison,
    latest: OrchestrationRunDetails,
    previous: OrchestrationRunDetails,
) -> str:
    signal_status = _status_map(
        reused_ids=comparison.reused_signal_ids,
        new_ids=comparison.new_signal_ids,
    )
    alert_status = _status_map(
        reused_ids=comparison.reused_alert_ids,
        new_ids=comparison.new_alert_ids,
    )
    sections = [
        f"compare latest two orchestration runs for {comparison.state_date.isoformat()}",
        f"latest_run_id: {comparison.latest_run_id}",
        f"latest_executed_at: {_format_datetime(comparison.latest_executed_at)}",
        f"previous_run_id: {comparison.previous_run_id}",
        f"previous_executed_at: {_format_datetime(comparison.previous_executed_at)}",
        (
            "state_fingerprint_changed: "
            + ("yes" if comparison.state_fingerprint_changed else "no")
        ),
        f"latest_state_fingerprint: {comparison.latest_state_fingerprint}",
        f"previous_state_fingerprint: {comparison.previous_state_fingerprint}",
        "",
        "signals",
        _render_signal_block(latest.signals, statuses=signal_status),
        "",
        "alerts",
        _render_alert_block(latest.alerts, statuses=alert_status),
        "",
        "latest_controller_events",
        _render_controller_event_block(latest.controller_events),
        "",
        "previous_controller_events",
        _render_controller_event_block(previous.controller_events),
        "",
    ]
    return "\n".join(sections)


def _render_signal_block(
    signals: list[Signal],
    *,
    statuses: dict[UUID, str] | None = None,
) -> str:
    if not signals:
        return "none"
    lines: list[str] = []
    for signal in signals:
        status_prefix = ""
        if statuses is not None:
            status_prefix = f"{statuses[signal.id]} "
        lines.append(
            f"- {status_prefix}{signal.severity} {signal.kind}: {signal.summary}"
        )
        lines.append(f"  reason: {signal.reason}")
        evidence_summaries = [item.summary for item in signal.evidence]
        if evidence_summaries:
            lines.append(f"  evidence: {'; '.join(evidence_summaries)}")
    return "\n".join(lines)


def _render_alert_block(
    alerts: list[Alert],
    *,
    statuses: dict[UUID, str] | None = None,
) -> str:
    if not alerts:
        return "none"
    lines: list[str] = []
    for alert in alerts:
        status_prefix = ""
        if statuses is not None:
            status_prefix = f"{statuses[alert.id]} "
        source_signal_ids = ", ".join(str(signal_id) for signal_id in alert.source_signal_ids)
        lines.append(
            f"- {status_prefix}{alert.escalation_level} {alert.channel} {alert.title}"
        )
        lines.append(f"  reason: {alert.reason}")
        lines.append(f"  source_signals: {source_signal_ids or 'none'}")
    return "\n".join(lines)


def _status_map(*, reused_ids: list[UUID], new_ids: list[UUID]) -> dict[UUID, str]:
    status_by_id = {entity_id: "reused" for entity_id in reused_ids}
    status_by_id.update({entity_id: "new" for entity_id in new_ids})
    return status_by_id


def _render_controller_event_block(events: list[ControllerEvent]) -> str:
    if not events:
        return "none"
    lines: list[str] = []
    for event in events:
        lines.append(
            f"- [{event.sequence_number}] {event.event_type}: {event.summary}"
        )
    return "\n".join(lines)


def _render_controller_summary(run: object) -> str:
    trajectory = getattr(run, "controller_trajectory", None)
    if trajectory is None:
        return "controller_outcome: none"
    return "\n".join(
        [
            f"controller_outcome: {trajectory.controller_outcome}",
            f"decision: {trajectory.decision.decision_summary}",
            f"authority: {trajectory.authority_result.outcome}",
        ]
    )


def _format_datetime(value: object) -> str:
    return str(value)
