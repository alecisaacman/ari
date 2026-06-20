from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from ari_state import (
    Alert,
    AuthorityOutcome,
    ControllerEvent,
    ControllerEventType,
    ControllerTrajectory,
    ControlOutcome,
    Signal,
)


def build_initial_controller_events(
    *,
    run_id: UUID,
    state_date: date,
    occurred_at: datetime,
    signals: list[Signal],
    alerts: list[Alert],
    trajectory: ControllerTrajectory,
) -> list[ControllerEvent]:
    events: list[ControllerEvent] = []
    _append_intake_event(
        events,
        run_id=run_id,
        state_date=state_date,
        occurred_at=occurred_at,
        signals=signals,
        alerts=alerts,
    )
    _append_decision_event(events, run_id=run_id, occurred_at=occurred_at, trajectory=trajectory)
    _append_authority_event(events, run_id=run_id, occurred_at=occurred_at, trajectory=trajectory)

    if trajectory.authority_result.outcome == AuthorityOutcome.REQUIRE_APPROVAL:
        _append_simple_event(
            events,
            run_id=run_id,
            occurred_at=occurred_at,
            event_type=ControllerEventType.APPROVAL_REQUESTED,
            summary="Approval was requested before execution could continue.",
            payload={
                "decision_id": str(trajectory.decision.id),
                "reason": trajectory.authority_result.reason,
            },
        )
        return events

    _append_execution_events(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        trajectory=trajectory,
    )
    _append_outcome_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        decision_id=trajectory.decision.id,
        controller_outcome=trajectory.controller_outcome,
    )
    return events


def build_approval_granted_events(
    *,
    run_id: UUID,
    sequence_start: int,
    occurred_at: datetime,
    decision_id: UUID,
) -> list[ControllerEvent]:
    events: list[ControllerEvent] = []
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.APPROVAL_GRANTED,
        summary="Approval was granted for the pending decision.",
        payload={"decision_id": str(decision_id)},
        sequence_start=sequence_start,
    )
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.CONTROLLER_RESUMED,
        summary="Controller resumed execution from approved pending state.",
        payload={"decision_id": str(decision_id)},
        sequence_start=sequence_start,
    )
    return events


def build_approval_denied_events(
    *,
    run_id: UUID,
    sequence_start: int,
    occurred_at: datetime,
    decision_id: UUID,
) -> list[ControllerEvent]:
    events: list[ControllerEvent] = []
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.APPROVAL_DENIED,
        summary="Approval was denied for the pending decision.",
        payload={"decision_id": str(decision_id)},
        sequence_start=sequence_start,
    )
    _append_outcome_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        decision_id=decision_id,
        controller_outcome=ControlOutcome.DENIED,
        sequence_start=sequence_start,
    )
    return events


def build_resumed_execution_events(
    *,
    run_id: UUID,
    sequence_start: int,
    occurred_at: datetime,
    trajectory: ControllerTrajectory,
) -> list[ControllerEvent]:
    events: list[ControllerEvent] = []
    _append_execution_events(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        trajectory=trajectory,
        sequence_start=sequence_start,
    )
    _append_outcome_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        decision_id=trajectory.decision.id,
        controller_outcome=trajectory.controller_outcome,
        sequence_start=sequence_start,
    )
    return events


def _append_intake_event(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    state_date: date,
    occurred_at: datetime,
    signals: list[Signal],
    alerts: list[Alert],
) -> None:
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.OBSERVATION_INTAKE,
        summary="Controller intake captured persisted signals and alerts.",
        payload={
            "state_date": state_date.isoformat(),
            "signal_ids": [str(signal.id) for signal in signals],
            "signal_kinds": [signal.kind for signal in signals],
            "alert_ids": [str(alert.id) for alert in alerts],
            "alert_titles": [alert.title for alert in alerts],
        },
    )


def _append_decision_event(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    occurred_at: datetime,
    trajectory: ControllerTrajectory,
) -> None:
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.DECISION_SELECTED,
        summary="Controller selected a canonical decision for this cycle.",
        payload={
            "decision_id": str(trajectory.decision.id),
            "decision_type": trajectory.decision.decision_type,
            "decision_summary": trajectory.decision.decision_summary,
            "proposed_action": trajectory.decision.proposed_action,
            "requires_approval": trajectory.decision.requires_approval,
            "confidence": trajectory.decision.confidence,
            "action_count": len(trajectory.decision.action_intents),
        },
    )


def _append_authority_event(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    occurred_at: datetime,
    trajectory: ControllerTrajectory,
) -> None:
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.AUTHORITY_RESULT,
        summary="Authority evaluation completed for the selected decision.",
        payload={
            "decision_id": str(trajectory.authority_result.decision_id),
            "outcome": trajectory.authority_result.outcome,
            "reason": trajectory.authority_result.reason,
            "may_execute": trajectory.authority_result.may_execute,
        },
    )


def _append_execution_events(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    occurred_at: datetime,
    trajectory: ControllerTrajectory,
    sequence_start: int = 0,
) -> None:
    if trajectory.action_plan is not None:
        _append_simple_event(
            events,
            run_id=run_id,
            occurred_at=occurred_at,
            event_type=ControllerEventType.DISPATCH_STARTED,
            summary="Bounded dispatch started for the allowed decision.",
            payload={
                "decision_id": str(trajectory.action_plan.decision_id),
                "summary": trajectory.action_plan.summary,
                "is_bounded": trajectory.action_plan.is_bounded,
                "actions": [
                    {
                        "action_type": action.action_type,
                        "target": action.target,
                        "instructions": action.instructions,
                    }
                    for action in trajectory.action_plan.actions
                ],
            },
            sequence_start=sequence_start,
        )

    if trajectory.worker_run is not None:
        _append_simple_event(
            events,
            run_id=run_id,
            occurred_at=occurred_at,
            event_type=ControllerEventType.DISPATCH_RESULT,
            summary="Dispatch returned execution observations.",
            payload={
                "decision_id": str(trajectory.worker_run.decision_id),
                "observation_count": len(trajectory.worker_run.observations),
                "observations": [
                    {
                        "success": observation.success,
                        "kind": observation.kind,
                        "target": observation.target,
                        "summary": observation.summary,
                    }
                    for observation in trajectory.worker_run.observations
                ],
            },
            sequence_start=sequence_start,
        )

    if trajectory.verification_result is not None:
        _append_simple_event(
            events,
            run_id=run_id,
            occurred_at=occurred_at,
            event_type=ControllerEventType.VERIFICATION_RESULT,
            summary="Verification resolved the execution result for the cycle.",
            payload={
                "decision_id": str(trajectory.verification_result.decision_id),
                "outcome": trajectory.verification_result.outcome,
                "reason": trajectory.verification_result.reason,
            },
            sequence_start=sequence_start,
        )


def _append_outcome_event(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    occurred_at: datetime,
    decision_id: UUID,
    controller_outcome: ControlOutcome,
    sequence_start: int = 0,
) -> None:
    _append_simple_event(
        events,
        run_id=run_id,
        occurred_at=occurred_at,
        event_type=ControllerEventType.CONTROLLER_OUTCOME,
        summary="Controller finalized the cycle outcome.",
        payload={
            "decision_id": str(decision_id),
            "controller_outcome": controller_outcome,
        },
        sequence_start=sequence_start,
    )


def _append_simple_event(
    events: list[ControllerEvent],
    *,
    run_id: UUID,
    occurred_at: datetime,
    event_type: ControllerEventType,
    summary: str,
    payload: dict[str, object],
    sequence_start: int = 0,
) -> None:
    events.append(
        ControllerEvent(
            run_id=run_id,
            sequence_number=sequence_start + len(events),
            occurred_at=occurred_at,
            event_type=event_type,
            summary=summary,
            payload=payload,
        )
    )
