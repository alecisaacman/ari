from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from ari_state import (
    Alert,
    AlertChannel,
    AlertEscalationLevel,
    DailyState,
    EvidenceItem,
    OpenLoop,
    Signal,
    SignalSeverity,
    WeeklyState,
)

OPEN_LOOP_WARNING_THRESHOLD = 7
OPEN_LOOP_CRITICAL_THRESHOLD = 12
ELEVATED_STRESS_WARNING_THRESHOLD = 8
ELEVATED_STRESS_CRITICAL_THRESHOLD = 9
STALE_OPEN_LOOP_DAYS = 7


def generate_signals(
    *,
    detected_at: datetime,
    daily_state: DailyState | None = None,
    weekly_state: WeeklyState | None = None,
    open_loops: Sequence[OpenLoop] = (),
) -> list[Signal]:
    signals: list[Signal] = []

    open_loop_signal = _build_open_loop_accumulation_signal(
        open_loops=open_loops,
        detected_at=detected_at,
    )
    if open_loop_signal is not None:
        signals.append(open_loop_signal)

    trajectory_signal = _build_weekly_trajectory_drift_signal(
        daily_state=daily_state,
        weekly_state=weekly_state,
        detected_at=detected_at,
    )
    if trajectory_signal is not None:
        signals.append(trajectory_signal)

    stress_signal = _build_elevated_stress_signal(
        daily_state=daily_state,
        detected_at=detected_at,
    )
    if stress_signal is not None:
        signals.append(stress_signal)

    return signals


def generate_alerts(
    signals: Sequence[Signal],
    *,
    created_at: datetime,
    channel: AlertChannel = AlertChannel.HUB,
) -> list[Alert]:
    return [
        Alert(
            channel=channel,
            escalation_level=_signal_to_escalation_level(signal),
            title=_signal_to_title(signal),
            message=signal.summary,
            reason=signal.reason,
            source_signal_ids=[signal.id],
            created_at=created_at,
        )
        for signal in signals
    ]


def _build_open_loop_accumulation_signal(
    *,
    open_loops: Sequence[OpenLoop],
    detected_at: datetime,
) -> Signal | None:
    total_open_loops = len(open_loops)
    if total_open_loops < OPEN_LOOP_WARNING_THRESHOLD:
        return None

    high_priority_count = sum(1 for loop in open_loops if loop.priority in {"high", "critical"})
    stale_before = detected_at - timedelta(days=STALE_OPEN_LOOP_DAYS)
    stale_loop_ids = [
        str(loop.id)
        for loop in open_loops
        if (loop.last_touched_at or loop.opened_at) <= stale_before
    ]
    severity = (
        SignalSeverity.CRITICAL
        if total_open_loops >= OPEN_LOOP_CRITICAL_THRESHOLD
        else SignalSeverity.WARNING
    )

    return Signal(
        kind="open_loop_accumulation",
        severity=severity,
        summary=f"{total_open_loops} open loops are active.",
        reason=(
            f"Open loops have accumulated past the operating threshold of "
            f"{OPEN_LOOP_WARNING_THRESHOLD}, raising the risk of silent drift."
        ),
        evidence=[
            EvidenceItem(
                kind="open_loop_stats",
                summary="Open loop volume exceeds the baseline threshold.",
                payload={
                    "total_open_loops": total_open_loops,
                    "high_priority_open_loops": high_priority_count,
                    "stale_open_loop_ids": stale_loop_ids,
                },
            ),
            EvidenceItem(
                kind="open_loop_sample",
                summary="Sample of active open loops contributing to the accumulation signal.",
                payload={
                    "loops": [
                        {
                            "id": str(loop.id),
                            "title": loop.title,
                            "priority": loop.priority,
                            "opened_at": loop.opened_at.isoformat(),
                        }
                        for loop in open_loops[:5]
                    ]
                },
            ),
        ],
        detected_at=detected_at,
    )


def _build_weekly_trajectory_drift_signal(
    *,
    daily_state: DailyState | None,
    weekly_state: WeeklyState | None,
    detected_at: datetime,
) -> Signal | None:
    if daily_state is None or weekly_state is None or not weekly_state.outcomes:
        return None

    aligned_outcomes = [
        outcome
        for outcome in weekly_state.outcomes
        if any(_has_token_overlap(outcome, priority) for priority in daily_state.priorities)
    ]
    if aligned_outcomes:
        return None

    return Signal(
        kind="weekly_trajectory_drift",
        severity=SignalSeverity.WARNING,
        summary="Today's priorities are not reinforcing this week's outcomes.",
        reason=(
            "No meaningful overlap was found between the weekly outcomes and today's top "
            "priorities, so day-level execution is drifting away from the declared week."
        ),
        evidence=[
            EvidenceItem(
                kind="weekly_state",
                summary="Current weekly plan used for trajectory comparison.",
                entity_type="weekly_state",
                payload={
                    "week_start": weekly_state.week_start.isoformat(),
                    "outcomes": weekly_state.outcomes,
                    "cannot_drift": weekly_state.cannot_drift,
                    "blockers": weekly_state.blockers,
                },
            ),
            EvidenceItem(
                kind="daily_state",
                summary="Current daily state compared against the weekly plan.",
                entity_type="daily_state",
                payload={
                    "date": daily_state.date.isoformat(),
                    "priorities": daily_state.priorities,
                    "movement": daily_state.movement,
                    "win_condition": daily_state.win_condition,
                },
            ),
        ],
        detected_at=detected_at,
    )


def _build_elevated_stress_signal(
    *,
    daily_state: DailyState | None,
    detected_at: datetime,
) -> Signal | None:
    if daily_state is None or daily_state.stress is None:
        return None
    if daily_state.stress < ELEVATED_STRESS_WARNING_THRESHOLD:
        return None

    severity = (
        SignalSeverity.CRITICAL
        if daily_state.stress >= ELEVATED_STRESS_CRITICAL_THRESHOLD
        else SignalSeverity.WARNING
    )
    return Signal(
        kind="elevated_stress",
        severity=severity,
        summary=f"Stress is elevated at {daily_state.stress}/10.",
        reason=(
            f"The latest daily check recorded stress at {daily_state.stress}/10, above the "
            f"elevated-stress threshold of {ELEVATED_STRESS_WARNING_THRESHOLD}."
        ),
        evidence=[
            EvidenceItem(
                kind="daily_state",
                summary="Stress evidence from the latest daily check.",
                entity_type="daily_state",
                payload={
                    "date": daily_state.date.isoformat(),
                    "stress": daily_state.stress,
                    "movement": daily_state.movement,
                    "next_action": daily_state.next_action,
                    "priorities": daily_state.priorities,
                },
            )
        ],
        detected_at=detected_at,
    )


def _signal_to_escalation_level(signal: Signal) -> AlertEscalationLevel:
    if signal.severity == SignalSeverity.CRITICAL:
        return AlertEscalationLevel.INTERRUPTIVE
    if signal.kind == "elevated_stress":
        return AlertEscalationLevel.ELEVATED
    if signal.kind == "weekly_trajectory_drift":
        return AlertEscalationLevel.ELEVATED
    return AlertEscalationLevel.VISIBLE


def _signal_to_title(signal: Signal) -> str:
    if signal.kind == "open_loop_accumulation":
        return "Open loops are accumulating"
    if signal.kind == "weekly_trajectory_drift":
        return "Weekly trajectory is drifting"
    if signal.kind == "elevated_stress":
        return "Stress is elevated"
    return "ARI surfaced a signal"


def _has_token_overlap(left: str, right: str) -> bool:
    return bool(_tokenize(left) & _tokenize(right))


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in "".join(char.lower() if char.isalnum() else " " for char in text).split()
        if len(token) > 2
    }
