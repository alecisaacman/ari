from __future__ import annotations

import hashlib
import json
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

    return RunSignalOrchestrationResult(
        run=run,
        signals=persisted_signals,
        alerts=persisted_alerts,
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
