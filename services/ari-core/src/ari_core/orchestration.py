from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ari_memory import (
    AlertRepository,
    DailyStateRepository,
    OpenLoopRepository,
    OrchestrationRunRepository,
    SignalRepository,
    WeeklyStateRepository,
)
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
from sqlalchemy.orm import Session

from .decision.controller import DecisionController
from .decision.models import Decision
from .modules.decision.dispatch import DispatchResult, dispatch_decision
from .modules.decision.evaluate import (
    EvaluationResult,
    LoopControlResult,
    evaluate_dispatch_result,
    summarize_evaluation_results,
)
from .modules.decision.persistence import PersistedDecisionTrail, persist_decision_trail


logger = logging.getLogger(__name__)
decision_controller = DecisionController()


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationInput:
    state_date: date
    detected_at: datetime
    alert_channel: AlertChannel = AlertChannel.HUB


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationResult:
    run: OrchestrationRun
    signals: list[Signal]
    alerts: list[Alert]
    decisions: list[Decision]
    dispatch_results: list[DispatchResult]
    evaluation_results: list[EvaluationResult]
    loop_control: LoopControlResult
    persisted_trail: PersistedDecisionTrail | None


def run_signal_orchestration(
    session: Session,
    orchestration_input: RunSignalOrchestrationInput,
) -> RunSignalOrchestrationResult:
    daily_states = DailyStateRepository(session)
    weekly_states = WeeklyStateRepository(session)
    open_loops = OpenLoopRepository(session)
    signals = SignalRepository(session)
    alerts = AlertRepository(session)
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
    controller_result = decision_controller.decide(
        signals=persisted_signals,
        state={
            "state_date": orchestration_input.state_date,
            "daily_state": None if daily_state is None else daily_state.model_dump(mode="json"),
            "weekly_state": None if weekly_state is None else weekly_state.model_dump(mode="json"),
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
    decisions = controller_result.decisions
    if decisions:
        logger.info(
            "ARI decisions generated for %s: %s",
            orchestration_input.state_date.isoformat(),
            [decision.to_dict() for decision in decisions],
        )
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
    if dispatch_results:
        logger.info(
            "ARI dispatch results for %s: %s",
            orchestration_input.state_date.isoformat(),
            [result.to_dict() for result in dispatch_results],
        )
    evaluation_results = [evaluate_dispatch_result(result) for result in dispatch_results]
    if evaluation_results:
        logger.info(
            "ARI evaluation results for %s: %s",
            orchestration_input.state_date.isoformat(),
            [result.to_dict() for result in evaluation_results],
        )
    loop_control = summarize_evaluation_results(evaluation_results)
    logger.info(
        "ARI loop control for %s: %s",
        orchestration_input.state_date.isoformat(),
        loop_control.to_dict(),
    )

    run = runs.create(
        OrchestrationRun(
            state_date=orchestration_input.state_date,
            state_fingerprint=state_fingerprint,
            executed_at=orchestration_input.detected_at,
            signal_ids=[signal.id for signal in persisted_signals],
            alert_ids=[alert.id for alert in persisted_alerts],
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

    return RunSignalOrchestrationResult(
        run=run,
        signals=persisted_signals,
        alerts=persisted_alerts,
        decisions=decisions,
        dispatch_results=dispatch_results,
        evaluation_results=evaluation_results,
        loop_control=loop_control,
        persisted_trail=persisted_trail,
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
