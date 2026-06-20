from __future__ import annotations

from ari_state import (
    AuthorityOutcome,
    ControllerCycleState,
    ControllerTrajectory,
    ControlOutcome,
)


def initial_controller_cycle_state(
    trajectory: ControllerTrajectory,
) -> ControllerCycleState:
    if trajectory.authority_result.outcome == AuthorityOutcome.REQUIRE_APPROVAL:
        return ControllerCycleState.WAITING_FOR_APPROVAL
    if trajectory.controller_outcome == ControlOutcome.DENIED:
        return ControllerCycleState.DENIED
    if trajectory.controller_outcome == ControlOutcome.SUCCESS:
        return ControllerCycleState.COMPLETED
    return ControllerCycleState.FAILED


def final_controller_cycle_state(
    trajectory: ControllerTrajectory,
) -> ControllerCycleState:
    if trajectory.controller_outcome == ControlOutcome.DENIED:
        return ControllerCycleState.DENIED
    if trajectory.controller_outcome == ControlOutcome.SUCCESS:
        return ControllerCycleState.COMPLETED
    return ControllerCycleState.FAILED
