from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ari_memory import (
    AlertRepository,
    DailyStateRepository,
    OpenLoopRepository,
    SignalRepository,
    WeeklyStateRepository,
)
from ari_signals import generate_alerts, generate_signals
from ari_state import Alert, AlertChannel, Signal
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationInput:
    state_date: date
    detected_at: datetime
    alert_channel: AlertChannel = AlertChannel.HUB


@dataclass(frozen=True, slots=True)
class RunSignalOrchestrationResult:
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

    daily_state = daily_states.get(orchestration_input.state_date)
    weekly_state = weekly_states.get(_week_start_for(orchestration_input.state_date))
    active_loops = open_loops.list_open()

    generated_signals = generate_signals(
        detected_at=orchestration_input.detected_at,
        daily_state=daily_state,
        weekly_state=weekly_state,
        open_loops=active_loops,
    )
    persisted_signals = signals.create_many(generated_signals)

    generated_alerts = generate_alerts(
        persisted_signals,
        created_at=orchestration_input.detected_at,
        channel=orchestration_input.alert_channel,
    )
    persisted_alerts = alerts.create_many(generated_alerts)

    session.commit()

    return RunSignalOrchestrationResult(
        signals=persisted_signals,
        alerts=persisted_alerts,
    )


def _week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())
