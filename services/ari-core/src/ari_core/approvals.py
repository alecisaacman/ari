from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ari_memory import (
    ControllerEventRepository,
    OrchestrationRunRepository,
    PendingApprovalRepository,
)
from ari_state import (
    ControllerCycleState,
    ControllerEvent,
    ControlOutcome,
    OrchestrationRun,
    PendingApproval,
    PendingApprovalStatus,
)
from sqlalchemy.orm import Session

from ari_core.controller import resume_controller_cycle
from ari_core.controller_events import (
    build_approval_denied_events,
    build_approval_granted_events,
    build_resumed_execution_events,
)
from ari_core.controller_state import final_controller_cycle_state


@dataclass(frozen=True, slots=True)
class ApprovalWorkflowResult:
    run: OrchestrationRun
    approval: PendingApproval
    controller_events: list[ControllerEvent]


def list_pending_approvals(session: Session) -> list[PendingApproval]:
    return PendingApprovalRepository(session).list_pending()


def approve_pending_approval(
    session: Session,
    *,
    approval_id: UUID,
    approved_at: datetime | None = None,
) -> ApprovalWorkflowResult | None:
    timestamp = approved_at or datetime.now(tz=UTC)
    approvals = PendingApprovalRepository(session)
    runs = OrchestrationRunRepository(session)
    controller_events = ControllerEventRepository(session)

    approval = approvals.get(approval_id)
    if approval is None:
        return None
    if approval.status != PendingApprovalStatus.PENDING:
        raise ValueError(f"Pending approval {approval_id} is already resolved.")

    run = runs.get(approval.run_id)
    if run is None or run.controller_trajectory is None:
        raise ValueError(f"No resumable controller run found for approval {approval_id}.")

    approval = approvals.update(
        approval.model_copy(
            update={
                "status": PendingApprovalStatus.APPROVED,
                "resolved_at": timestamp,
            }
        )
    )
    run = runs.update(
        run.model_copy(
            update={
                "controller_cycle_state": ControllerCycleState.RESUMED,
            }
        )
    )
    existing_events = controller_events.list_for_run(run.id)
    granted_events = controller_events.create_many(
        build_approval_granted_events(
            run_id=run.id,
            sequence_start=len(existing_events),
            occurred_at=timestamp,
            decision_id=approval.decision_id,
        )
    )
    session.commit()

    resumed_trajectory = resume_controller_cycle(
        run.controller_trajectory,
        resumed_at=timestamp,
    )
    final_run = runs.update(
        run.model_copy(
            update={
                "controller_trajectory": resumed_trajectory,
                "controller_cycle_state": final_controller_cycle_state(resumed_trajectory),
            }
        )
    )
    resumed_events = controller_events.create_many(
        build_resumed_execution_events(
            run_id=final_run.id,
            sequence_start=len(existing_events) + len(granted_events),
            occurred_at=timestamp,
            trajectory=resumed_trajectory,
        )
    )
    session.commit()
    return ApprovalWorkflowResult(
        run=final_run,
        approval=approval,
        controller_events=[*granted_events, *resumed_events],
    )


def deny_pending_approval(
    session: Session,
    *,
    approval_id: UUID,
    denied_at: datetime | None = None,
) -> ApprovalWorkflowResult | None:
    timestamp = denied_at or datetime.now(tz=UTC)
    approvals = PendingApprovalRepository(session)
    runs = OrchestrationRunRepository(session)
    controller_events = ControllerEventRepository(session)

    approval = approvals.get(approval_id)
    if approval is None:
        return None
    if approval.status != PendingApprovalStatus.PENDING:
        raise ValueError(f"Pending approval {approval_id} is already resolved.")

    run = runs.get(approval.run_id)
    if run is None or run.controller_trajectory is None:
        raise ValueError(f"No controller run found for approval {approval_id}.")

    approval = approvals.update(
        approval.model_copy(
            update={
                "status": PendingApprovalStatus.DENIED,
                "resolved_at": timestamp,
            }
        )
    )
    denied_trajectory = run.controller_trajectory.model_copy(
        update={"controller_outcome": ControlOutcome.DENIED}
    )
    run = runs.update(
        run.model_copy(
            update={
                "controller_trajectory": denied_trajectory,
                "controller_cycle_state": ControllerCycleState.DENIED,
            }
        )
    )
    existing_events = controller_events.list_for_run(run.id)
    denied_events = controller_events.create_many(
        build_approval_denied_events(
            run_id=run.id,
            sequence_start=len(existing_events),
            occurred_at=timestamp,
            decision_id=approval.decision_id,
        )
    )
    session.commit()
    return ApprovalWorkflowResult(
        run=run,
        approval=approval,
        controller_events=denied_events,
    )
