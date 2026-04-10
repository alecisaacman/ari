from datetime import date, datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from ari_state import (
    Alert,
    AlertChannel,
    AlertEscalationLevel,
    DailyState,
    EvidenceItem,
    OpenLoop,
    OpenLoopPriority,
    OpenLoopStatus,
    Signal,
    SignalSeverity,
    WeeklyState,
)


def test_daily_state_serializes_canonical_fields() -> None:
    state = DailyState(
        date=date(2026, 4, 10),
        priorities=["Ship correction pass", "Lock canonical schema"],
        win_condition="The repo contract matches the ARI doctrine.",
        movement=True,
        stress=6,
        next_action="Update migrations and tests.",
    )

    payload = state.model_dump(mode="json")

    assert payload["date"] == "2026-04-10"
    assert payload["priorities"] == ["Ship correction pass", "Lock canonical schema"]
    assert payload["movement"] is True
    assert payload["stress"] == 6
    assert payload["next_action"] == "Update migrations and tests."


def test_daily_state_rejects_more_than_three_priorities() -> None:
    with pytest.raises(ValidationError):
        DailyState(
            date=date(2026, 4, 10),
            priorities=["one", "two", "three", "four"],
        )


def test_weekly_state_rejects_more_than_three_outcomes() -> None:
    with pytest.raises(ValidationError):
        WeeklyState(
            week_start=date(2026, 4, 7),
            outcomes=["one", "two", "three", "four"],
        )


def test_daily_state_rejects_out_of_range_stress() -> None:
    with pytest.raises(ValidationError):
        DailyState(
            date=date(2026, 4, 10),
            stress=11,
        )


def test_open_loop_round_trips_uuid_and_enums() -> None:
    loop = OpenLoop(
        title="Close the migration loop",
        status=OpenLoopStatus.IN_PROGRESS,
        priority=OpenLoopPriority.HIGH,
        source="operator",
        opened_at=datetime(2026, 4, 10, 8, 0, tzinfo=timezone.utc),
    )

    payload = loop.model_dump(mode="json")

    assert UUID(payload["id"])
    assert payload["status"] == "in_progress"
    assert payload["priority"] == "high"


def test_signal_and_alert_preserve_explainability_contract() -> None:
    signal = Signal(
        kind="drift_risk",
        severity=SignalSeverity.WARNING,
        summary="Priority movement has slowed.",
        reason="No meaningful movement was recorded against the top priority since yesterday.",
        evidence=[
            EvidenceItem(
                kind="daily_state",
                summary="DailyState movement field remained unchanged.",
                entity_type="daily_state",
            )
        ],
        detected_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
    )

    alert = Alert(
        channel=AlertChannel.NOTIFICATION,
        escalation_level=AlertEscalationLevel.INTERRUPTIVE,
        title="Trajectory is slipping",
        message="Top priority movement has stalled.",
        reason="Escalated because the drift signal persisted across checks.",
        source_signal_ids=[signal.id],
        created_at=datetime(2026, 4, 10, 9, 5, tzinfo=timezone.utc),
    )

    signal_payload = signal.model_dump(mode="json")
    alert_payload = alert.model_dump(mode="json")

    assert signal_payload["evidence"][0]["kind"] == "daily_state"
    assert "top priority" in signal_payload["reason"]
    assert alert_payload["source_signal_ids"] == [str(signal.id)]
    assert alert_payload["escalation_level"] == "interruptive"
