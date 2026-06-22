from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from ari_memory import (
    AlertRepository,
    DailyStateRepository,
    OpenLoopRepository,
    OrchestrationRunRepository,
    SignalRepository,
    WeeklyStateRepository,
)

try:
    from ari_memory import ControllerEventRepository, PendingApprovalRepository
except ImportError:  # pragma: no cover - supports focused tests with partial fakes.
    ControllerEventRepository = None  # type: ignore[assignment]
    PendingApprovalRepository = None  # type: ignore[assignment]
from ari_signals import generate_alerts, generate_signals
from ari_state import (
    Alert,
    AlertChannel,
    DailyState,
    OpenLoop,
    OrchestrationRun,
    Signal,
    WeeklyState,
)

try:
    from ari_state import ControllerDecision, ControllerEvent, ControllerTrajectory, PendingApproval
except ImportError:  # pragma: no cover - supports focused tests with partial fakes.
    ControllerDecision = object  # type: ignore[misc,assignment]
    ControllerEvent = object  # type: ignore[misc,assignment]
    ControllerTrajectory = object  # type: ignore[misc,assignment]
    PendingApproval = object  # type: ignore[misc,assignment]
from sqlalchemy.orm import Session

try:
    from ari_core.controller import run_controller_cycle
    from ari_core.controller_events import build_initial_controller_events
    from ari_core.controller_state import initial_controller_cycle_state
except ImportError:  # pragma: no cover - supports focused tests with partial fakes.
    run_controller_cycle = None  # type: ignore[assignment]
    build_initial_controller_events = None  # type: ignore[assignment]
    initial_controller_cycle_state = None  # type: ignore[assignment]
from ari_core.decision.controller import DecisionController
from ari_core.decision.models import Decision
from ari_core.modules.decision.dispatch import DispatchResult, dispatch_decision
from ari_core.modules.decision.evaluate import (
    EvaluationResult,
    LoopControlResult,
    evaluate_dispatch_result,
    summarize_evaluation_results,
)
from ari_core.modules.decision.persistence import PersistedDecisionTrail, persist_decision_trail

logger = logging.getLogger(__name__)
decision_controller = DecisionController()


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
    decisions: list[Decision] | None = None
    dispatch_results: list[DispatchResult] | None = None
    evaluation_results: list[EvaluationResult] | None = None
    loop_control: LoopControlResult | None = None
    persisted_trail: PersistedDecisionTrail | None = None


def run_signal_orchestration(
    session: Session,
    orchestration_input: RunSignalOrchestrationInput,
) -> RunSignalOrchestrationResult:
    daily_states = DailyStateRepository(session)
    weekly_states = WeeklyStateRepository(session)
    open_loops = OpenLoopRepository(session)
    signals = SignalRepository(session)
    alerts = AlertRepository(session)
    controller_events = None if ControllerEventRepository is None else ControllerEventRepository(session)
    pending_approvals = None if PendingApprovalRepository is None else PendingApprovalRepository(session)
    runs = OrchestrationRunRepository(session)

    daily_state = daily_states.get(orchestration_input.state_date)
    weekly_state = weekly_states.get(_week_start_for(orchestration_input.state_date))
    active_loops = open_loops.list_open()
    recent_signals = signals.list_recent(limit=100)
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
    controller_result = (
        None
        if orchestration_input.controller_decision is not None
        else decision_controller.decide(
            signals=persisted_signals,
            state={
                "state_date": orchestration_input.state_date,
                "daily_state": (
                    None if daily_state is None else daily_state.model_dump(mode="json")
                ),
                "weekly_state": (
                    None if weekly_state is None else weekly_state.model_dump(mode="json")
                ),
                "open_loop_count": len(active_loops),
                "repeated_signal_ids": [
                    str(signal.id)
                    for signal in persisted_signals
                    if any(previous.kind == signal.kind for previous in recent_signals)
                ],
            },
            run_context={
                "alert_channel": orchestration_input.alert_channel,
                "detected_at": orchestration_input.detected_at.isoformat(),
            },
        )
    )
    decisions = [] if controller_result is None else controller_result.decisions
    actionable_decisions = [
        decision
        for decision in decisions
        if decision.decision_type == "act" and bool(decision.action)
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
    dispatch_results = [dispatch_decision(decision) for decision in actionable_decisions]
    evaluation_results = [evaluate_dispatch_result(result) for result in dispatch_results]
    loop_control = summarize_evaluation_results(evaluation_results)
    controller_trajectory = (
        None
        if orchestration_input.controller_decision is None
        else run_controller_cycle(
            orchestration_input.controller_decision,
            executed_at=orchestration_input.detected_at,
        )
    )

    run = runs.create(
        _build_orchestration_run(
            state_date=orchestration_input.state_date,
            state_fingerprint=state_fingerprint,
            executed_at=orchestration_input.detected_at,
            signal_ids=[signal.id for signal in persisted_signals],
            alert_ids=[alert.id for alert in persisted_alerts],
            controller_trajectory=controller_trajectory,
        )
    )
    pending_approval = (
        None
        if (
            controller_trajectory is None
            or pending_approvals is None
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
        if (
            controller_trajectory is None
            or controller_events is None
            or build_initial_controller_events is None
        )
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
    persisted_trail = None
    if decisions:
        persisted_trail = persist_decision_trail(
            orchestration_run_id=str(run.id),
            decisions=decisions,
            dispatch_results=dispatch_results,
            evaluation_results=evaluation_results,
            loop_control=loop_control,
        )
        logger.info(
            "ARI persisted decision trail for %s: %s decisions, %s dispatches, %s evaluations, cycle=%s",
            orchestration_input.state_date.isoformat(),
            len(persisted_trail.decisions),
            len(persisted_trail.dispatches),
            len(persisted_trail.evaluations),
            None if persisted_trail.cycle is None else persisted_trail.cycle["status"],
        )

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
        decisions=decisions,
        dispatch_results=dispatch_results,
        evaluation_results=evaluation_results,
        loop_control=loop_control,
        persisted_trail=persisted_trail,
    )


def _week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _build_orchestration_run(
    *,
    state_date: date,
    state_fingerprint: str,
    executed_at: datetime,
    signal_ids: list[object],
    alert_ids: list[object],
    controller_trajectory: ControllerTrajectory | None,
) -> OrchestrationRun:
    payload = {
        "state_date": state_date,
        "state_fingerprint": state_fingerprint,
        "executed_at": executed_at,
        "signal_ids": signal_ids,
        "alert_ids": alert_ids,
    }
    if initial_controller_cycle_state is not None:
        payload["controller_trajectory"] = controller_trajectory
        payload["controller_cycle_state"] = (
            None
            if controller_trajectory is None
            else initial_controller_cycle_state(controller_trajectory)
        )
    try:
        return OrchestrationRun(**payload)
    except TypeError:
        payload.pop("controller_trajectory", None)
        payload.pop("controller_cycle_state", None)
        return OrchestrationRun(**payload)


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
