from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from ari_memory import (
    AlertRepository,
    ControllerEventRepository,
    DailyStateRepository,
    OpenLoopRepository,
    OrchestrationRunRepository,
    PendingApprovalRepository,
    SignalRepository,
    WeeklyStateRepository,
)
from ari_signals import generate_alerts, generate_signals
from ari_state import (
    Alert,
    AlertChannel,
    ControllerDecision,
    ControllerEvent,
    ControllerTrajectory,
    DailyState,
    OpenLoop,
    OrchestrationRun,
    PendingApproval,
    Signal,
    WeeklyState,
)
from sqlalchemy.orm import Session

from ari_core.controller import run_controller_cycle
from ari_core.controller_events import build_initial_controller_events
from ari_core.controller_state import initial_controller_cycle_state


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationInput:
    state_date: date
    detected_at: datetime
    alert_channel: AlertChannel = AlertChannel.HUB
    controller_decision: ControllerDecision | None = None


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationResult:
    run: OrchestrationRun
    signals: list[Signal]
    alerts: list[Alert]
    controller_trajectory: ControllerTrajectory | None = None
    controller_events: list[ControllerEvent] | None = None
    pending_approval: PendingApproval | None = None


def run_signal_orchestration(
    session: Session,
    orchestration_input: RunSignalOrchestrationInput,
) -> RunSignalOrchestrationResult:
    daily_states = DailyStateRepository(session)
    weekly_states = WeeklyStateRepository(session)
    open_loops = OpenLoopRepository(session)
    signals = SignalRepository(session)
    alerts = AlertRepository(session)
    controller_events = ControllerEventRepository(session)
    pending_approvals = PendingApprovalRepository(session)
    runs = OrchestrationRunRepository(session)

    daily_state = daily_states.get(orchestration_input.state_date)
    weekly_state = weekly_states.get(_week_start_for(orchestration_input.state_date))
    active_loops = open_loops.list_open()
    state_fingerprint = _build_state_fingerprint(
        state_date=orchestration_input.state_date,
        daily_state=daily_state,
        weekly_state=weekly_state,
        open_loops=active_loops,
    )

    generated_signals = generate_signals(
        detected_at=orchestration_input.detected_at,
        daily_state=daily_state,
        weekly_state=weekly_state,
        open_loops=active_loops,
    )
    persisted_signals = [
        _persist_signal(
            repository=signals,
            state_date=orchestration_input.state_date,
            signal=signal,
        )
        for signal in generated_signals
    ]

    generated_alerts = generate_alerts(
        persisted_signals,
        created_at=orchestration_input.detected_at,
        channel=orchestration_input.alert_channel,
    )
    persisted_alerts = [
        _persist_alert(
            repository=alerts,
            state_date=orchestration_input.state_date,
            alert=alert,
        )
        for alert in generated_alerts
    ]
    controller_trajectory = (
        None
        if orchestration_input.controller_decision is None
        else run_controller_cycle(
            orchestration_input.controller_decision,
            executed_at=orchestration_input.detected_at,
        )
    )

    run = runs.create(
        OrchestrationRun(
            state_date=orchestration_input.state_date,
            state_fingerprint=state_fingerprint,
            executed_at=orchestration_input.detected_at,
            signal_ids=[signal.id for signal in persisted_signals],
            alert_ids=[alert.id for alert in persisted_alerts],
            controller_trajectory=controller_trajectory,
            controller_cycle_state=(
                None
                if controller_trajectory is None
                else initial_controller_cycle_state(controller_trajectory)
            ),
        )
    )
    pending_approval = (
        None
        if (
            controller_trajectory is None
            or controller_trajectory.authority_result.outcome != "require_approval"
        )
        else pending_approvals.create(
            PendingApproval(
                run_id=run.id,
                decision_id=controller_trajectory.decision.id,
                requested_at=orchestration_input.detected_at,
                reason=controller_trajectory.authority_result.reason,
                decision_summary=controller_trajectory.decision.decision_summary,
                proposed_action=controller_trajectory.decision.proposed_action,
            )
        )
    )
    persisted_controller_events = (
        []
        if controller_trajectory is None
        else controller_events.create_many(
            build_initial_controller_events(
                run_id=run.id,
                state_date=orchestration_input.state_date,
                occurred_at=orchestration_input.detected_at,
                signals=persisted_signals,
                alerts=persisted_alerts,
                trajectory=controller_trajectory,
            )
        )
    )

    session.commit()

    _write_daily_log(
        run=run,
        signals=persisted_signals,
        alerts=persisted_alerts,
    )

    return RunSignalOrchestrationResult(
        run=run,
        signals=persisted_signals,
        alerts=persisted_alerts,
        controller_trajectory=controller_trajectory,
        controller_events=persisted_controller_events,
        pending_approval=pending_approval,
    )


def _week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _persist_signal(
    *,
    repository: SignalRepository,
    state_date: date,
    signal: Signal,
) -> Signal:
    fingerprint = _signal_fingerprint(state_date=state_date, signal=signal)
    existing = repository.get_by_fingerprint(state_date=state_date, fingerprint=fingerprint)
    if existing is not None:
        return existing
    return repository.create(
        signal.model_copy(update={"state_date": state_date, "fingerprint": fingerprint})
    )


def _persist_alert(
    *,
    repository: AlertRepository,
    state_date: date,
    alert: Alert,
) -> Alert:
    fingerprint = _alert_fingerprint(state_date=state_date, alert=alert)
    existing = repository.get_by_fingerprint(state_date=state_date, fingerprint=fingerprint)
    if existing is not None:
        return existing
    return repository.create(
        alert.model_copy(update={"state_date": state_date, "fingerprint": fingerprint})
    )


def _build_state_fingerprint(
    *,
    state_date: date,
    daily_state: DailyState | None,
    weekly_state: WeeklyState | None,
    open_loops: list[OpenLoop],
) -> str:
    payload = {
        "state_date": state_date.isoformat(),
        "daily_state": None if daily_state is None else daily_state.model_dump(mode="json"),
        "weekly_state": None if weekly_state is None else weekly_state.model_dump(mode="json"),
        "open_loops": [
            loop.model_dump(mode="json")
            for loop in sorted(open_loops, key=lambda loop: str(loop.id))
        ],
    }
    return _fingerprint(payload)


def _signal_fingerprint(*, state_date: date, signal: Signal) -> str:
    payload = {
        "state_date": state_date.isoformat(),
        "kind": signal.kind,
        "severity": signal.severity,
        "summary": signal.summary,
        "reason": signal.reason,
        "evidence": [item.model_dump(mode="json") for item in signal.evidence],
        "related_entity_type": signal.related_entity_type,
        "related_entity_id": (
            None if signal.related_entity_id is None else str(signal.related_entity_id)
        ),
    }
    return _fingerprint(payload)


def _alert_fingerprint(*, state_date: date, alert: Alert) -> str:
    payload = {
        "state_date": state_date.isoformat(),
        "channel": alert.channel,
        "escalation_level": alert.escalation_level,
        "title": alert.title,
        "message": alert.message,
        "reason": alert.reason,
        "source_signal_ids": sorted(str(signal_id) for signal_id in alert.source_signal_ids),
    }
    return _fingerprint(payload)


def _fingerprint(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _write_daily_log(
    *,
    run: OrchestrationRun,
    signals: list[Signal],
    alerts: list[Alert],
) -> None:
    logs_dir = Path(
        os.environ.get(
            "ARI_LOGS_DIR",
            str(Path(__file__).resolve().parents[4] / "logs"),
        )
    )
    daily_dir = logs_dir / "daily"
    try:
        daily_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    log_path = daily_dir / f"{run.state_date.isoformat()}.md"
    lines: list[str] = [
        f"## Run {run.id}",
        "",
        f"**Executed at:** {run.executed_at.isoformat()}  ",
        f"**State fingerprint:** `{run.state_fingerprint}`",
        "",
    ]

    if signals:
        lines.append(f"### Signals ({len(signals)})")
        lines.append("")
        for sig in signals:
            lines.append(f"- `{sig.kind}` — {sig.severity} — {sig.summary}")
        lines.append("")
    else:
        lines.append("_No signals detected._")
        lines.append("")

    if alerts:
        lines.append(f"### Alerts ({len(alerts)})")
        lines.append("")
        for alert in alerts:
            lines.append(f"- [{alert.escalation_level.upper()}] {alert.title}")
        lines.append("")
    else:
        lines.append("_No alerts generated._")
        lines.append("")

    lines.append("---")
    lines.append("")

    header_needed = not log_path.exists()
    with log_path.open("a", encoding="utf-8") as f:
        if header_needed:
            f.write(f"# Orchestration Log — {run.state_date.isoformat()}\n\n")
        f.write("\n".join(lines))
