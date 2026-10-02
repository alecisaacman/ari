from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ActionIdempotencyState,
    CheckpointState,
    ContinuationAcknowledgement,
    ExecutionLedger,
    ExecutionSessionManager,
    ExecutionTaskSpec,
    RecoveredActionGateway,
    ResumeDecision,
    TaskLifecycleState,
    WorkerAction,
    WorkerPlan,
    classify_effect_terminality,
)

_DEFAULT = object()


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass(slots=True)
class RecoveredFixture:
    db_path: Path
    root: Path
    clock: FixedClock
    ledger: ExecutionLedger
    sessions: ExecutionSessionManager
    gateway: RecoveredActionGateway
    task_id: str
    old_attempt_id: str
    attempt_id: str
    worker_identity: str
    session_id: str
    action_ids: tuple[str, ...]

    def resume(self):
        return self.gateway.resume_one(
            task_id=self.task_id,
            attempt_id=self.attempt_id,
            worker_identity=self.worker_identity,
            session_id=self.session_id,
        )


def _recovered_task(
    tmp_path: Path,
    *,
    steps: int = 2,
    approval_required: bool = False,
    restrictions: tuple[str, ...] = ("no network", "no automatic side effects"),
    step_two_path: str = "step-two.txt",
    action_executor=None,
    before_execute_hook=None,
    effect_terminality: Any = _DEFAULT,
    step_two_action: tuple[str, dict[str, Any]] | None = None,
    permitted_side_effects: tuple[str, ...] = ("write_file",),
) -> RecoveredFixture:
    """Build a task recovered onto a replacement worker with step two pending.

    Test executors run their effects in-process unless a test says otherwise, so the
    gateway classifies them like the built-in executor by default. Pass
    `effect_terminality=None` to get the gateway's own default for an injected executor.
    """
    if effect_terminality is _DEFAULT:
        effect_terminality = classify_effect_terminality
    step_two_type, step_two_payload = step_two_action or (
        "write_file",
        {"path": step_two_path, "content": "step two complete\n"},
    )
    db_path = tmp_path / "ari.db"
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    for index in range(1, steps + 1):
        (root / f"step-{['one', 'two', 'three'][index - 1]}.txt").write_text(
            "step one complete\n" if index == 1 else "not done\n",
            encoding="utf-8",
        )
    clock = FixedClock(datetime(2026, 10, 1, 12, 0, tzinfo=UTC))
    ledger = ExecutionLedger(db_path)
    task_id = f"task-gateway-{tmp_path.name}"
    _, old_attempt_id = ledger.create_task(
        ExecutionTaskSpec(
            task_id=task_id,
            objective="Finish the recovered bounded task.",
            success_criteria=("All planned file writes verify.",),
            restrictions=restrictions,
            authority_scope={
                "filesystem": [
                    "step-one.txt",
                    "step-two.txt",
                    "step-three.txt",
                ],
                "permitted_side_effects": list(permitted_side_effects),
            },
            approval_state={
                "required": approval_required,
                "status": "pending" if approval_required else "not_required",
            },
            authority_snapshot_ref="authority-gateway-1",
            authority_snapshot_hash="sha256:gateway-authority",
        ),
        executor_id="original-worker",
        backend_id="current-backend",
        provenance={"source": "gateway-test"},
    )
    sessions = ExecutionSessionManager(db_path, clock=clock)
    sessions.acquire_lease(
        task_id=task_id,
        attempt_id=old_attempt_id,
        worker_identity="original-worker",
        lease_seconds=5,
    )

    actions = [
        WorkerAction(
            id="action-step-one",
            action_type="write_file",
            payload={"path": "step-one.txt", "content": "step one complete\n"},
            reason="Complete step one.",
        ),
        WorkerAction(
            id="action-step-two",
            action_type=step_two_type,
            payload=step_two_payload,
            reason="Complete step two.",
        ),
    ]
    if steps == 3:
        actions.append(
            WorkerAction(
                id="action-step-three",
                action_type="write_file",
                payload={"path": "step-three.txt", "content": "step three complete\n"},
                reason="Complete step three.",
            )
        )
    plan = WorkerPlan(actions=tuple(actions), verification=(), reason="Bounded recovery plan.")
    pending = tuple(
        {
            "action_id": action.id,
            "action_type": action.action_type,
            "reason": action.reason,
        }
        for action in actions[1:]
    )
    ledger.record_boundary(
        task_id=task_id,
        attempt_id=old_attempt_id,
        trigger="action_completed",
        event_type="action.action_completed",
        state=CheckpointState(
            objective="Finish the recovered bounded task.",
            success_criteria=("All planned file writes verify.",),
            current_plan=plan.to_dict(),
            completed_steps=(
                {
                    "action_id": actions[0].id,
                    "action_type": actions[0].action_type,
                    "verified": True,
                },
            ),
            pending_steps=pending,
            artifacts=(
                {
                    "path": "step-one.txt",
                    "action_id": actions[0].id,
                    "action_type": actions[0].action_type,
                },
            ),
            actions_taken=(
                {
                    "action_id": actions[0].id,
                    "action_type": actions[0].action_type,
                    "result": {"success": True, "verified": True},
                },
            ),
            verification_results=(
                {"action_id": actions[0].id, "verified": True},
            ),
            provider={"executor_id": "original-worker", "backend_id": "current-backend"},
            next_recommended_action="Complete step two.",
            provenance={"source": "gateway-test", "worker": "original-worker"},
            restrictions=restrictions,
            authority_scope={
                "filesystem": [
                    "step-one.txt",
                    "step-two.txt",
                    "step-three.txt",
                ],
                "permitted_side_effects": list(permitted_side_effects),
            },
            approval_state={
                "required": approval_required,
                "status": "pending" if approval_required else "not_required",
            },
        ),
    )
    clock.advance(seconds=6)
    worker_identity = "replacement-worker"
    recovery = sessions.reconcile_stale_attempt(
        old_attempt_id,
        replacement_worker_identity=worker_identity,
        lease_seconds=300,
    )
    assert recovery.replacement_attempt_id is not None
    assert recovery.continuation_packet_id is not None
    _acknowledge(
        ledger,
        sessions,
        packet_id=recovery.continuation_packet_id,
        worker_identity=worker_identity,
    )
    current = sessions.inspect_task(task_id)
    assert current is not None
    attempt_id = str(recovery.replacement_attempt_id)
    session_id = str(current["session"]["active_attempt"]["session_id"])
    gateway = RecoveredActionGateway(
        db_path,
        execution_root=root,
        clock=clock,
        pause_state_reader=lambda: {"paused": False, "reason": None},
        action_executor=action_executor,
        before_execute_hook=before_execute_hook,
        effect_terminality=effect_terminality,
    )
    return RecoveredFixture(
        db_path=db_path,
        root=root,
        clock=clock,
        ledger=ledger,
        sessions=sessions,
        gateway=gateway,
        task_id=task_id,
        old_attempt_id=old_attempt_id,
        attempt_id=attempt_id,
        worker_identity=worker_identity,
        session_id=session_id,
        action_ids=tuple(action.id for action in actions),
    )


def _acknowledge(
    ledger: ExecutionLedger,
    sessions: ExecutionSessionManager,
    *,
    packet_id: str,
    worker_identity: str,
) -> None:
    stored = ledger._one(
        "select * from ari_execution_continuation_packets where packet_id = ?",
        (packet_id,),
    )
    assert stored is not None
    packet = stored["packet"]
    sessions.acknowledge_continuation(
        packet_id=packet_id,
        worker_identity=worker_identity,
        acknowledgement=ContinuationAcknowledgement(
            objective=packet["objective"],
            completed_steps=tuple(packet["completed_steps"]),
            pending_steps=tuple(packet["pending_steps"]),
            restrictions=tuple(packet["restrictions"]),
            authority_scope=packet["authority_scope"],
            authority_snapshot_ref=packet["authority_snapshot_ref"],
            next_proposed_action=packet["recommended_next_action"],
        ),
    )


def _replace_worker(recovered: RecoveredFixture) -> RecoveredFixture:
    """Let the current replacement lease expire and recover onto a further worker."""
    recovered.clock.advance(seconds=301)
    worker_identity = f"{recovered.worker_identity}-next"
    recovery = recovered.sessions.reconcile_stale_attempt(
        recovered.attempt_id,
        replacement_worker_identity=worker_identity,
        lease_seconds=300,
    )
    assert recovery.replacement_attempt_id is not None
    assert recovery.continuation_packet_id is not None
    _acknowledge(
        recovered.ledger,
        recovered.sessions,
        packet_id=recovery.continuation_packet_id,
        worker_identity=worker_identity,
    )
    attempt = recovered.ledger._one(
        "select * from ari_execution_attempts where attempt_id = ?",
        (recovery.replacement_attempt_id,),
    )
    assert attempt is not None
    return replace(
        recovered,
        attempt_id=str(recovery.replacement_attempt_id),
        worker_identity=worker_identity,
        session_id=str(attempt["session_id"]),
    )


def _revise_step_two(recovered: RecoveredFixture, content: str) -> None:
    """Record a canonical plan revision that changes action-step-two's digest."""
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    plan = dict(checkpoint["current_plan"])
    actions = [dict(item) for item in plan["actions"]]
    actions[1] = {
        **actions[1],
        "payload": {"path": "step-two.txt", "content": content},
        "execution_action": {"type": "write_file", "path": "step-two.txt", "content": content},
    }
    plan["actions"] = actions
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(checkpoint, current_plan=plan),
    )


def _counting_executor(calls: list[dict[str, Any]]):
    from ari_core.modules.execution import execute_action

    def executor(action: dict[str, Any], root: Path | str | None) -> dict[str, Any]:
        calls.append(action)
        return execute_action(action, root)

    return executor


def _execution_rows(recovered: RecoveredFixture) -> list[dict[str, Any]]:
    return recovered.gateway.inspect_task(recovered.task_id)["executions"]


def _step_two(recovered: RecoveredFixture) -> str:
    return (recovered.root / "step-two.txt").read_text(encoding="utf-8")


def test_execution_ready_task_proposes_one_action_without_executing(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path)

    proposal = recovered.gateway.propose_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
    )

    assert proposal.action_id == "action-step-two"
    assert proposal.proposed_action["path"] == "step-two.txt"
    assert proposal.idempotency_state is ActionIdempotencyState.NEVER_ATTEMPTED
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"
    assert recovered.gateway.inspect_task(recovered.task_id)["decisions"] == []


def test_valid_authority_and_approval_execute_exactly_once(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path, approval_required=True)
    approval = recovered.gateway.approve_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        approved_by="alec",
        reason="Approve this exact recovered file write.",
    )

    result = recovered.resume()
    duplicate = recovered.resume()
    bundle = recovered.ledger.get_task_bundle(recovered.task_id)
    inspection = recovered.gateway.inspect_task(recovered.task_id)

    assert result.decision is ResumeDecision.ALLOW
    assert result.executed is True
    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert result.approval_reference == approval["approval_id"]
    assert result.pre_checkpoint_id is not None
    assert result.result_checkpoint_id is not None
    assert result.verification_checkpoint_id is not None
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == (
        "step two complete\n"
    )
    assert duplicate.executed is False
    assert duplicate.decision is ResumeDecision.DENY
    assert duplicate.idempotency_state is ActionIdempotencyState.ALREADY_COMPLETED
    assert bundle is not None
    latest = bundle["checkpoints"][-1]
    assert latest["pending_steps"] == []
    assert latest["completed_steps"][-1]["action_id"] == "action-step-two"
    assert latest["completed_steps"][-1]["verified"] is True
    session_inspection = recovered.sessions.inspect_task(recovered.task_id)
    assert session_inspection is not None
    assert session_inspection["session"]["execution_resumed"] is True
    result_checkpoint = next(
        item for item in bundle["checkpoints"] if item["checkpoint_id"] == result.result_checkpoint_id
    )
    verification_checkpoint = next(
        item
        for item in bundle["checkpoints"]
        if item["checkpoint_id"] == result.verification_checkpoint_id
    )
    assert result_checkpoint["actions_taken"][-1]["result"]["success"] is True
    assert verification_checkpoint["verification_results"][-1]["verified"] is True
    assert verification_checkpoint["artifacts"][-1]["sha256"]
    assert len(inspection["executions"]) == 1
    assert inspection["executions"][0]["state"] == "succeeded"


def test_missing_approval_stops_without_worker_failure(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path, approval_required=True)

    result = recovered.resume()
    task = recovered.ledger.get_task(recovered.task_id)
    attempt = recovered.ledger._one(
        "select * from ari_execution_attempts where attempt_id = ?",
        (recovered.attempt_id,),
    )

    assert result.decision is ResumeDecision.REQUIRE_APPROVAL
    assert result.executed is False
    assert task is not None and task["lifecycle_state"] == "awaiting_approval"
    assert attempt is not None and attempt["lifecycle_state"] == "awaiting_approval"
    assert attempt["status"] != "failed"
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"

    recovered.gateway.approve_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        approved_by="alec",
        reason="Approve after the durable approval stop.",
    )
    resumed = recovered.resume()
    assert resumed.idempotency_state is ActionIdempotencyState.SUCCEEDED


def test_expired_approval_stops_execution(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path, approval_required=True)
    recovered.gateway.approve_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        approved_by="alec",
        reason="Short approval.",
        expires_at=recovered.clock() + timedelta(seconds=5),
    )
    recovered.clock.advance(seconds=6)

    result = recovered.resume()

    assert result.decision is ResumeDecision.REQUIRE_APPROVAL
    assert "expired" in result.reason
    assert result.executed is False


def test_changed_action_digest_invalidates_prior_approval(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path, approval_required=True)
    approved = recovered.gateway.approve_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        approved_by="alec",
        reason="Approve original content.",
    )
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    plan = dict(checkpoint["current_plan"])
    actions = [dict(item) for item in plan["actions"]]
    actions[1] = {
        **actions[1],
        "payload": {"path": "step-two.txt", "content": "materially changed\n"},
        "execution_action": {
            "type": "write_file",
            "path": "step-two.txt",
            "content": "materially changed\n",
        },
    }
    plan["actions"] = actions
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(
            checkpoint,
            current_plan=plan,
        ),
    )

    result = recovered.resume()

    assert result.decision is ResumeDecision.REQUIRE_APPROVAL
    assert result.approval_reference != approved["approval_id"]
    assert result.executed is False
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"


@pytest.mark.parametrize(
    "state",
    [TaskLifecycleState.PAUSED, TaskLifecycleState.CANCELLED, TaskLifecycleState.BLOCKED],
)
def test_explicit_task_gate_prevents_execution(
    tmp_path: Path,
    state: TaskLifecycleState,
) -> None:
    recovered = _recovered_task(tmp_path)
    recovered.sessions.set_task_lifecycle(recovered.task_id, state, reason=f"test {state}")

    result = recovered.resume()
    task = recovered.ledger.get_task(recovered.task_id)

    assert result.executed is False
    assert result.decision in {ResumeDecision.DENY, ResumeDecision.BLOCKED}
    assert task is not None and task["lifecycle_state"] == state
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"


def test_stale_lease_and_superseded_attempt_cannot_execute(tmp_path: Path) -> None:
    stale = _recovered_task(tmp_path / "stale")
    stale.clock.advance(seconds=301)
    stale_result = stale.resume()

    superseded = _recovered_task(tmp_path / "superseded")
    new_attempt = superseded.ledger.start_attempt(
        superseded.task_id,
        executor_id="newer-worker",
        backend_id="current-backend",
    )
    with superseded.ledger._transaction() as connection:
        connection.execute(
            "update ari_execution_tasks set active_attempt_id = ? where task_id = ?",
            (new_attempt, superseded.task_id),
        )
    superseded_result = superseded.resume()

    assert stale_result.executed is False
    assert "stale" in stale_result.reason
    assert superseded_result.executed is False
    assert "superseded" in superseded_result.reason


def test_global_pause_and_wrong_session_identity_prevent_execution(tmp_path: Path) -> None:
    paused = _recovered_task(tmp_path / "paused")
    paused.gateway.pause_state_reader = lambda: {
        "paused": True,
        "reason": "operator kill switch",
    }
    paused_result = paused.resume()

    wrong_session = _recovered_task(tmp_path / "wrong-session")
    identity_result = wrong_session.gateway.resume_one(
        task_id=wrong_session.task_id,
        attempt_id=wrong_session.attempt_id,
        worker_identity=wrong_session.worker_identity,
        session_id="session-not-owner",
    )

    assert paused_result.executed is False
    assert "Global execution pause" in paused_result.reason
    paused_task = paused.ledger.get_task(paused.task_id)
    assert paused_task is not None
    assert paused_task["lifecycle_state"] == "execution_ready"
    assert identity_result.executed is False
    assert "does not own" in identity_result.reason


def test_authority_scope_cannot_widen_and_restrictions_are_enforced(tmp_path: Path) -> None:
    widened = _recovered_task(tmp_path / "widened")
    with widened.ledger._transaction() as connection:
        connection.execute(
            "update ari_execution_tasks set authority_scope_json = ? where task_id = ?",
            ('{"filesystem":["/"],"permitted_side_effects":["write_file"]}', widened.task_id),
        )
    widened_result = widened.resume()

    restricted = _recovered_task(tmp_path / "restricted", restrictions=("read only",))
    restricted_result = restricted.resume()

    assert widened_result.executed is False
    assert "scope changed" in widened_result.reason
    assert restricted_result.executed is False
    assert "prohibit file mutation" in restricted_result.reason


def test_sandbox_escape_is_blocked(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path, step_two_path="../escape.txt")

    result = recovered.resume()

    assert result.decision is ResumeDecision.BLOCKED
    assert "escapes execution root" in result.reason
    assert not (tmp_path / "escape.txt").exists()


def test_uncertain_side_effect_is_not_blindly_retried(tmp_path: Path) -> None:
    calls = 0

    def uncertain_executor(_action: dict[str, Any], _root: Path | str | None):
        nonlocal calls
        calls += 1
        raise RuntimeError("worker vanished during dispatch")

    recovered = _recovered_task(tmp_path, action_executor=uncertain_executor)

    first = recovered.resume()
    second = recovered.resume()

    assert first.executed is True
    assert first.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert second.executed is False
    assert second.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert calls == 1
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"


def test_pause_arriving_after_authorization_stops_before_effect(tmp_path: Path) -> None:
    holder: dict[str, RecoveredFixture] = {}

    def pause_before_execute(_proposal) -> None:
        fixture = holder["fixture"]
        assert (fixture.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"
        execution = fixture.gateway.inspect_task(fixture.task_id)["latest_execution"]
        assert execution["pre_checkpoint_id"] is not None
        assert execution["state"] == "authorized_not_run"
        fixture.sessions.set_task_lifecycle(
            fixture.task_id,
            TaskLifecycleState.PAUSED,
            reason="pause raced with resume",
        )

    recovered = _recovered_task(tmp_path, before_execute_hook=pause_before_execute)
    holder["fixture"] = recovered

    result = recovered.resume()

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert result.pre_checkpoint_id is not None
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == "not done\n"


def test_verification_is_required_before_completion(tmp_path: Path) -> None:
    def lying_executor(action: dict[str, Any], root: Path | str | None):
        target = Path(root) / str(action["path"])
        target.write_text("wrong content\n", encoding="utf-8")
        return {"success": True, "path": str(action["path"])}

    recovered = _recovered_task(tmp_path, action_executor=lying_executor)

    result = recovered.resume()
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)

    assert result.idempotency_state is ActionIdempotencyState.VERIFICATION_FAILED
    assert result.verification == {
        "verified": False,
        "evidence": result.verification["evidence"],
    }
    assert latest["pending_steps"][0]["action_id"] == "action-step-two"
    assert all(
        item["action_id"] != "action-step-two" for item in latest["completed_steps"]
    )
    retry = recovered.resume()
    assert retry.executed is False
    assert retry.idempotency_state is ActionIdempotencyState.VERIFICATION_FAILED


def test_three_step_resume_executes_step_two_and_leaves_step_three_untouched(
    tmp_path: Path,
) -> None:
    recovered = _recovered_task(tmp_path, steps=3)

    result = recovered.resume()
    bundle = recovered.ledger.get_task_bundle(recovered.task_id)
    assert bundle is not None
    latest = bundle["checkpoints"][-1]
    triggers = [checkpoint["trigger"] for checkpoint in bundle["checkpoints"]]

    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert (recovered.root / "step-two.txt").read_text(encoding="utf-8") == (
        "step two complete\n"
    )
    assert (recovered.root / "step-three.txt").read_text(encoding="utf-8") == "not done\n"
    assert latest["completed_steps"][-1]["action_id"] == "action-step-two"
    assert [item["action_id"] for item in latest["pending_steps"]] == [
        "action-step-three"
    ]
    assert triggers[-3:] == [
        "before_authorized_action",
        "action_result_persisted",
        "action_verification_completed",
    ]
    assert recovered.gateway.inspect_task(recovered.task_id)["one_action_limit"] is True


class SimulatedCrash(BaseException):
    """Process death: escapes the gateway's ordinary exception handling."""


def test_concurrent_resume_dispatches_exactly_once(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    rival = RecoveredActionGateway(
        recovered.db_path,
        execution_root=recovered.root,
        clock=recovered.clock,
        pause_state_reader=lambda: {"paused": False, "reason": None},
        action_executor=_counting_executor(calls),
    )
    original_gate = recovered.gateway._evaluate_gate
    rival_results = []

    def gate_then_race(proposal, **kwargs):
        outcome = original_gate(proposal, **kwargs)
        if not rival_results:
            rival_results.append(
                rival.resume_one(
                    task_id=recovered.task_id,
                    attempt_id=recovered.attempt_id,
                    worker_identity=recovered.worker_identity,
                    session_id=recovered.session_id,
                )
            )
        return outcome

    recovered.gateway._evaluate_gate = gate_then_race  # type: ignore[method-assign]

    result = recovered.resume()

    assert rival_results[0].idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert result.decision is ResumeDecision.DENY
    assert result.executed is False
    assert len(calls) == 1
    assert len(_execution_rows(recovered)) == 1
    assert _step_two(recovered) == "step two complete\n"


def test_duplicate_request_during_reserved_window_is_denied(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    duplicates = []
    holder: dict[str, RecoveredFixture] = {}

    def duplicate_before_dispatch(_proposal) -> None:
        duplicates.append(holder["fixture"].resume())

    recovered = _recovered_task(
        tmp_path,
        action_executor=_counting_executor(calls),
        before_execute_hook=duplicate_before_dispatch,
    )
    holder["fixture"] = recovered

    result = recovered.resume()

    assert duplicates[0].decision is ResumeDecision.DENY
    assert duplicates[0].idempotency_state is ActionIdempotencyState.AUTHORIZED_NOT_RUN
    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 1


def test_checkpoint_moving_between_gate_and_reservation_reserves_nothing(
    tmp_path: Path,
) -> None:
    recovered = _recovered_task(tmp_path)
    original_gate = recovered.gateway._evaluate_gate
    raced: list[bool] = []

    def gate_then_concurrent_write(proposal, **kwargs):
        outcome = original_gate(proposal, **kwargs)
        if not raced:
            raced.append(True)
            checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
            recovered.ledger.record_boundary(
                task_id=recovered.task_id,
                attempt_id=recovered.attempt_id,
                trigger="finding_recorded",
                event_type="finding.recorded",
                state=RecoveredActionGateway._checkpoint_state(
                    checkpoint,
                    next_recommended_action="A concurrent writer advanced the checkpoint.",
                ),
            )
        return outcome

    recovered.gateway._evaluate_gate = gate_then_concurrent_write  # type: ignore[method-assign]

    first = recovered.resume()

    assert first.decision is ResumeDecision.DENY
    assert first.idempotency_state is ActionIdempotencyState.NEVER_ATTEMPTED
    assert "changed after the gate decision" in first.reason
    assert _execution_rows(recovered) == []
    assert _step_two(recovered) == "not done\n"

    second = recovered.resume()
    assert second.idempotency_state is ActionIdempotencyState.SUCCEEDED


def test_pending_action_changed_after_reservation_is_not_dispatched(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    holder: dict[str, RecoveredFixture] = {}

    def revise_before_dispatch(_proposal) -> None:
        _revise_step_two(holder["fixture"], "swapped after authorization\n")

    recovered = _recovered_task(
        tmp_path,
        action_executor=_counting_executor(calls),
        before_execute_hook=revise_before_dispatch,
    )
    holder["fixture"] = recovered

    result = recovered.resume()

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert "changed after authorization" in result.reason
    assert calls == []
    assert _step_two(recovered) == "not done\n"
    assert _execution_rows(recovered)[0]["state"] == "failed_before_effect"


def test_revised_digest_cannot_rerun_an_uncertain_action(tmp_path: Path) -> None:
    calls = 0

    def uncertain_executor(_action: dict[str, Any], _root: Path | str | None):
        nonlocal calls
        calls += 1
        raise RuntimeError("connection reset after write was sent")

    recovered = _recovered_task(tmp_path, action_executor=uncertain_executor)
    first = recovered.resume()
    _revise_step_two(recovered, "same step, different digest\n")

    proposal = recovered.gateway.propose_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
    )
    second = recovered.resume()

    assert first.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert proposal.action_digest != first.proposal.action_digest
    assert proposal.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert second.executed is False
    assert second.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert calls == 1


def test_stopped_before_effect_action_runs_only_after_explicit_revision(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    paused = {"value": False, "armed": True}

    def pause_once(_proposal) -> None:
        if paused["armed"]:
            paused["armed"] = False
            paused["value"] = True

    recovered = _recovered_task(
        tmp_path,
        action_executor=_counting_executor(calls),
        before_execute_hook=pause_once,
    )
    recovered.gateway.pause_state_reader = lambda: {
        "paused": paused["value"],
        "reason": "operator kill switch",
    }

    stopped = recovered.resume()
    paused["value"] = False
    same_digest = recovered.resume()
    _revise_step_two(recovered, "step two complete\n ")
    revised = recovered.resume()

    assert stopped.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert same_digest.executed is False
    assert same_digest.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert revised.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 1


def test_crash_after_dispatch_is_uncertain_for_replacement_worker(tmp_path: Path) -> None:
    calls = 0

    def crashing_executor(action: dict[str, Any], root: Path | str | None):
        nonlocal calls
        calls += 1
        (Path(root) / str(action["path"])).write_text(str(action["content"]), encoding="utf-8")
        raise SimulatedCrash()

    recovered = _recovered_task(tmp_path, action_executor=crashing_executor)
    with pytest.raises(SimulatedCrash):
        recovered.resume()

    assert _execution_rows(recovered)[0]["state"] == "executing"
    same_worker = recovered.resume()
    assert same_worker.executed is False
    assert same_worker.idempotency_state is ActionIdempotencyState.EXECUTING

    replacement = _replace_worker(recovered)
    replacement_result = replacement.resume()
    again = replacement.resume()
    latest = replacement.gateway._latest_checkpoint(replacement.task_id)

    assert replacement_result.executed is False
    assert replacement_result.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert again.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert _execution_rows(replacement)[0]["state"] == "effect_may_have_occurred"
    assert [item["action_id"] for item in latest["pending_steps"]] == ["action-step-two"]
    assert calls == 1


def test_crash_between_reservation_and_dispatch_never_reaches_the_effect(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    crash = {"armed": True}

    def crash_before_dispatch(_proposal) -> None:
        if crash["armed"]:
            raise SimulatedCrash()

    recovered = _recovered_task(
        tmp_path,
        action_executor=_counting_executor(calls),
        before_execute_hook=crash_before_dispatch,
    )
    with pytest.raises(SimulatedCrash):
        recovered.resume()

    reserved = _execution_rows(recovered)[0]
    assert reserved["state"] == "authorized_not_run"
    assert reserved["pre_checkpoint_id"] is not None

    crash["armed"] = False
    replacement = _replace_worker(recovered)
    result = replacement.resume()

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert _execution_rows(replacement)[0]["state"] == "failed_before_effect"
    assert _execution_rows(replacement)[0]["effect_status"] == "not_started"
    assert calls == []
    assert _step_two(replacement) == "not done\n"


@pytest.mark.parametrize(
    ("failing_trigger", "expected_effect_status", "expected_result_recorded"),
    [
        ("action_result_persisted", "dispatch_started", False),
        ("action_verification_completed", "result_recorded", True),
    ],
)
def test_persistence_failure_after_effect_is_atomic_and_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_trigger: str,
    expected_effect_status: str,
    expected_result_recorded: bool,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    original_insert = ExecutionLedger._insert_boundary

    def failing_insert(connection, **kwargs):
        if kwargs["trigger"] == failing_trigger:
            raise sqlite3.OperationalError("disk I/O error")
        return original_insert(connection, **kwargs)

    monkeypatch.setattr(ExecutionLedger, "_insert_boundary", staticmethod(failing_insert))

    with pytest.raises(sqlite3.OperationalError):
        recovered.resume()

    monkeypatch.undo()
    row = _execution_rows(recovered)[0]
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)
    assert row["state"] == "executing"
    assert row["effect_status"] == expected_effect_status
    assert (row["result"] is not None) is expected_result_recorded
    assert row["verification_checkpoint_id"] is None
    assert [item["action_id"] for item in latest["pending_steps"]] == ["action-step-two"]
    assert _step_two(recovered) == "step two complete\n"

    assert recovered.resume().executed is False
    replacement = _replace_worker(recovered)
    replacement_result = replacement.resume()
    assert replacement_result.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert len(calls) == 1


def test_attempt_superseded_mid_action_cannot_advance_canonical_state(
    tmp_path: Path,
) -> None:
    holder: dict[str, RecoveredFixture] = {}
    replacements: list[RecoveredFixture] = []

    def slow_executor(action: dict[str, Any], root: Path | str | None):
        replacements.append(_replace_worker(holder["fixture"]))
        (Path(root) / str(action["path"])).write_text(str(action["content"]), encoding="utf-8")
        return {"success": True, "path": str(action["path"])}

    recovered = _recovered_task(tmp_path, action_executor=slow_executor)
    holder["fixture"] = recovered
    checkpoint_before = recovered.gateway._latest_checkpoint(recovered.task_id)

    result = recovered.resume()
    row = _execution_rows(recovered)[0]
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)

    assert result.executed is True
    assert result.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert result.result_checkpoint_id is None
    assert row["state"] == "effect_may_have_occurred"
    assert row["result"]["success"] is True
    assert latest["sequence"] == checkpoint_before["sequence"] + 1  # pre-action only
    assert latest["trigger"] == "before_authorized_action"
    assert [item["action_id"] for item in latest["pending_steps"]] == ["action-step-two"]

    replacement_result = replacements[0].resume()
    assert replacement_result.executed is False
    assert replacement_result.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN


@pytest.mark.parametrize(
    ("pending_steps", "plan_actions", "message"),
    [
        (({"action_type": "write_file"},), None, "action_id is required"),
        (({"action_id": "action-missing"},), None, "absent from the canonical plan"),
        (
            ({"action_id": "action-step-two"},),
            [{"id": "action-step-two", "payload": "not-a-dict"}],
            "malformed payload",
        ),
        (
            ({"action_id": "action-step-two"},),
            [{"id": "action-step-two", "payload": {}}],
            "no action type",
        ),
    ],
)
def test_malformed_persisted_action_fails_closed(
    tmp_path: Path,
    pending_steps: tuple[dict[str, Any], ...],
    plan_actions: list[dict[str, Any]] | None,
    message: str,
) -> None:
    recovered = _recovered_task(tmp_path)
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    plan = dict(checkpoint["current_plan"])
    if plan_actions is not None:
        plan["actions"] = plan_actions
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(
            checkpoint,
            current_plan=plan,
            pending_steps=pending_steps,
        ),
    )

    with pytest.raises(ValueError, match=message):
        recovered.resume()
    inspection = recovered.sessions.inspect_task(recovered.task_id)

    assert inspection is not None
    assert inspection["recovered_action_gateway"]["proposed_action"] is None
    assert _execution_rows(recovered) == []
    assert _step_two(recovered) == "not done\n"
