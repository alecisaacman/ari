from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ari_core.modules.execution import (
    ContinuationAcknowledgement,
    ExecutionController,
    ExecutionGoal,
    ExecutionLedger,
    ExecutionSessionManager,
    ExecutionTaskSpec,
    ModelPlanner,
    RecoveryClassification,
    TaskLifecycleState,
)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _create_task(ledger: ExecutionLedger, task_id: str = "task-session-test") -> tuple[str, str]:
    return ledger.create_task(
        ExecutionTaskSpec(
            task_id=task_id,
            objective="Recover a bounded execution session.",
            success_criteria=("Canonical state identifies the next safe action.",),
            restrictions=("no network", "no automatic side effects"),
            authority_scope={"filesystem": ["proof/"]},
            approval_state={"required": False},
            authority_snapshot_ref="authority-session-1",
            authority_snapshot_hash="sha256:session-authority",
        ),
        executor_id="current-worker",
        backend_id="current-backend",
        provenance={"source": "recovery-test"},
    )


def test_healthy_lease_and_heartbeat_extend_liveness(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    clock = FixedClock(datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    ledger = ExecutionLedger(db_path)
    task_id, attempt_id = _create_task(ledger)
    sessions = ExecutionSessionManager(db_path, clock=clock)

    worker_session = sessions.acquire_lease(
        task_id=task_id,
        attempt_id=attempt_id,
        worker_identity="worker-a",
        worker_session_ref="process-101",
        lease_seconds=10,
    )
    initial_expiration = worker_session.lease.expires_at
    assert sessions.classify_attempt(attempt_id).classification is RecoveryClassification.HEALTHY

    clock.advance(seconds=5)
    heartbeat = sessions.heartbeat(
        attempt_id=attempt_id,
        worker_identity="worker-a",
        extend_seconds=10,
        metadata={"capacity": "available"},
    )

    assert heartbeat.lease_expires_at > initial_expiration
    inspection = sessions.inspect_task(task_id)
    assert inspection is not None
    assert inspection["session"]["lease_healthy"] is True
    assert inspection["session"]["last_heartbeat_at"] == heartbeat.observed_at

    clock.advance(seconds=16)
    stale = sessions.classify_attempt(attempt_id)
    assert stale.classification is RecoveryClassification.STALE
    assert stale.recoverable is True


@pytest.mark.parametrize(
    ("state", "classification"),
    [
        (TaskLifecycleState.AWAITING_APPROVAL, RecoveryClassification.AWAITING_APPROVAL),
        (TaskLifecycleState.BLOCKED, RecoveryClassification.BLOCKED),
        (TaskLifecycleState.PAUSED, RecoveryClassification.PAUSED),
        (TaskLifecycleState.CANCELLED, RecoveryClassification.CANCELLED),
    ],
)
def test_expired_attempt_does_not_recover_through_explicit_gates(
    tmp_path: Path,
    state: TaskLifecycleState,
    classification: RecoveryClassification,
) -> None:
    db_path = tmp_path / state / "ari.db"
    clock = FixedClock(datetime(2026, 9, 30, 13, 0, tzinfo=UTC))
    ledger = ExecutionLedger(db_path)
    task_id, attempt_id = _create_task(ledger)
    sessions = ExecutionSessionManager(db_path, clock=clock)
    sessions.acquire_lease(
        task_id=task_id,
        attempt_id=attempt_id,
        worker_identity="worker-a",
        lease_seconds=5,
    )
    clock.advance(seconds=6)
    sessions.set_task_lifecycle(task_id, state, reason=f"explicit {state} gate")

    decision = sessions.reconcile_stale_attempt(
        attempt_id,
        replacement_worker_identity="worker-b",
        lease_seconds=10,
    )
    bundle = ledger.get_task_bundle(task_id)

    assert decision.classification is classification
    assert decision.recoverable is False
    assert decision.replacement_attempt_id is None
    assert bundle is not None
    assert len(bundle["attempts"]) == 1


def test_stale_worker_recovery_prepares_acknowledged_session_without_step_two(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ari.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "step-one.txt").write_text("not done\n", encoding="utf-8")
    (root / "step-two.txt").write_text("not done\n", encoding="utf-8")
    clock = FixedClock(datetime(2026, 9, 30, 14, 0, tzinfo=UTC))
    sessions = ExecutionSessionManager(db_path, clock=clock)
    planner = ModelPlanner(
        lambda _payload: json.dumps(
            {
                "confidence": 0.99,
                "reason": "Perform two checkpointed steps.",
                "actions": [
                    {
                        "type": "write_file",
                        "path": "step-one.txt",
                        "content": "step one complete\n",
                        "reason": "Complete Step 1.",
                    },
                    {
                        "type": "write_file",
                        "path": "step-two.txt",
                        "content": "step two complete\n",
                        "reason": "Complete Step 2.",
                    },
                ],
            }
        )
    )

    class SimulatedWorkerDisappearance(BaseException):
        pass

    def disappear_after_step_one(trigger: str, payload: dict[str, object]) -> None:
        checkpoint = payload["checkpoint"]
        assert isinstance(checkpoint, dict)
        if trigger == "action_completed" and len(checkpoint["completed_steps"]) == 1:
            raise SimulatedWorkerDisappearance

    goal = ExecutionGoal(
        task_id="task-stale-worker-e2e",
        objective="Complete two steps without repeating completed work.",
        success_criteria=("Both steps eventually complete under ARI authority.",),
        restrictions=("no network", "no automatic side effects during recovery"),
        authority_scope={"filesystem": ["step-one.txt", "step-two.txt"]},
        approval_state={"required": False, "status": "not_required"},
        authority_snapshot_ref="authority-e2e-1",
        authority_snapshot_hash="sha256:e2e-authority",
    )
    controller = ExecutionController(
        execution_root=root,
        db_path=db_path,
        planner=planner,
        lifecycle_hook=disappear_after_step_one,
        session_manager=sessions,
        worker_lease_seconds=10,
    )

    with pytest.raises(SimulatedWorkerDisappearance):
        controller.run(goal)

    assert (root / "step-one.txt").read_text(encoding="utf-8") == "step one complete\n"
    assert (root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"

    ledger = ExecutionLedger(db_path)
    before = ledger.get_task_bundle(goal.task_id)
    assert before is not None
    old_attempt_id = before["task"]["active_attempt_id"]
    source_checkpoint_id = before["task"]["latest_checkpoint_id"]
    clock.advance(seconds=11)

    stale = sessions.classify_attempt(old_attempt_id)
    assert stale.classification is RecoveryClassification.STALE
    recovery = sessions.reconcile_stale_attempt(
        old_attempt_id,
        replacement_worker_identity="worker-replacement",
        worker_session_ref="process-replacement",
        lease_seconds=30,
    )

    assert recovery.task_id == goal.task_id
    assert recovery.replacement_attempt_id is not None
    assert recovery.replacement_attempt_id != old_attempt_id
    assert recovery.latest_checkpoint_id == source_checkpoint_id
    assert recovery.continuation_packet_id is not None

    awaiting_ack = sessions.inspect_task(goal.task_id)
    assert awaiting_ack is not None
    packet_row = awaiting_ack["session"]["continuation_packet"]
    assert packet_row is not None
    packet = packet_row["packet"]
    assert packet["objective"] == goal.objective
    assert packet["success_criteria"] == list(goal.success_criteria)
    assert packet["completed_steps"][0]["action_type"] == "write_file"
    assert packet["pending_steps"][0]["action_type"] == "write_file"
    assert packet["artifacts"][0]["path"] == "step-one.txt"
    assert len(packet["artifacts"][0]["sha256"]) == 64
    assert packet["restrictions"] == list(goal.restrictions)
    assert packet["authority_scope"] == goal.authority_scope
    assert packet["approval_state"] == goal.approval_state
    assert packet["authority_snapshot_ref"] == goal.authority_snapshot_ref
    assert packet["checkpoint_id"] == source_checkpoint_id
    assert awaiting_ack["session"]["continuation_acknowledgement"] is None
    assert awaiting_ack["task"]["lifecycle_state"] == (
        "awaiting_continuation_acknowledgement"
    )
    assert (root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"

    acknowledgement = ContinuationAcknowledgement(
        objective=packet["objective"],
        completed_steps=tuple(packet["completed_steps"]),
        pending_steps=tuple(packet["pending_steps"]),
        restrictions=tuple([*packet["restrictions"], "no privilege expansion"]),
        authority_scope=packet["authority_scope"],
        authority_snapshot_ref=packet["authority_snapshot_ref"],
        next_proposed_action=packet["recommended_next_action"],
    )
    stored_ack = sessions.acknowledge_continuation(
        packet_id=recovery.continuation_packet_id,
        worker_identity="worker-replacement",
        acknowledgement=acknowledgement,
    )
    recovered = sessions.inspect_task(goal.task_id)

    assert stored_ack["worker_identity"] == "worker-replacement"
    assert recovered is not None
    assert recovered["task"]["lifecycle_state"] == "execution_ready"
    assert recovered["session"]["active_attempt_id"] == recovery.replacement_attempt_id
    assert recovered["session"]["active_attempt"]["prior_attempt_id"] == old_attempt_id
    assert recovered["session"]["continuation_acknowledgement"] is not None
    assert recovered["session"]["next_action"] == packet["recommended_next_action"]
    assert recovered["session"]["execution_resumed"] is False
    assert "authority/tool gateway" in recovered["session"]["resume_blocked_reason"]
    assert (root / "step-one.txt").read_text(encoding="utf-8") == "step one complete\n"
    assert (root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"

    attempts = recovered["attempts"]
    old_attempt = next(item for item in attempts if item["attempt_id"] == old_attempt_id)
    replacement = next(
        item for item in attempts if item["attempt_id"] == recovery.replacement_attempt_id
    )
    assert old_attempt["lifecycle_state"] == "stale"
    assert old_attempt["replacement_attempt_id"] == replacement["attempt_id"]
    assert replacement["lifecycle_state"] == "execution_ready"
    event_types = [event["event_type"] for event in recovered["events"]]
    assert "worker.stale" in event_types
    assert "recovery.continuation_prepared" in event_types
    assert "continuation.acknowledged" in event_types

    second_reconciliation = sessions.reconcile_stale_attempt(
        old_attempt_id,
        replacement_worker_identity="worker-duplicate",
        lease_seconds=30,
    )
    after_duplicate_check = sessions.inspect_task(goal.task_id)
    assert second_reconciliation.classification is RecoveryClassification.TERMINAL
    assert second_reconciliation.replacement_attempt_id is None
    assert after_duplicate_check is not None
    assert len(after_duplicate_check["attempts"]) == 2


def test_acknowledgement_cannot_widen_authority_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    clock = FixedClock(datetime(2026, 9, 30, 15, 0, tzinfo=UTC))
    ledger = ExecutionLedger(db_path)
    task_id, attempt_id = _create_task(ledger)
    sessions = ExecutionSessionManager(db_path, clock=clock)
    sessions.acquire_lease(
        task_id=task_id,
        attempt_id=attempt_id,
        worker_identity="worker-a",
        lease_seconds=2,
    )
    clock.advance(seconds=3)
    recovery = sessions.reconcile_stale_attempt(
        attempt_id,
        replacement_worker_identity="worker-b",
        lease_seconds=10,
    )
    inspection = sessions.inspect_task(task_id)
    assert inspection is not None
    packet = inspection["session"]["continuation_packet"]["packet"]

    with pytest.raises(ValueError, match="authority_scope"):
        sessions.acknowledge_continuation(
            packet_id=str(recovery.continuation_packet_id),
            worker_identity="worker-b",
            acknowledgement=ContinuationAcknowledgement(
                objective=packet["objective"],
                completed_steps=tuple(packet["completed_steps"]),
                pending_steps=tuple(packet["pending_steps"]),
                restrictions=tuple(packet["restrictions"]),
                authority_scope={"filesystem": ["/"]},
                authority_snapshot_ref=packet["authority_snapshot_ref"],
                next_proposed_action=packet["recommended_next_action"],
            ),
        )

    after = sessions.inspect_task(task_id)
    assert after is not None
    assert after["task"]["lifecycle_state"] == "awaiting_continuation_acknowledgement"
    assert after["session"]["continuation_acknowledgement"] is None
