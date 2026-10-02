from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ActionIdempotencyState,
    DispatchFences,
    DispatchFenceState,
    DispatchQuiescenceUnproven,
    EffectReconciler,
    EffectReconciliationOutcome,
    ExecutionRoot,
    RecoveredActionGateway,
    ResumeDecision,
    execute_action,
)
from ari_core.modules.execution.dispatch import DispatchFenceRejected, DispatchLock
from ari_core.modules.execution.sandbox import DISPATCH_HOLD_FDS
from test_effect_reconciliation import ABSENT_EVIDENCE, PRESENT_EVIDENCE
from test_recovered_action_gateway import (
    RecoveredFixture,
    SimulatedCrash,
    _counting_executor,
    _execution_rows,
    _recovered_task,
    _replace_worker,
    _revise_step_two,
    _step_two,
)

ABSENT = EffectReconciliationOutcome.EFFECT_CONFIRMED_ABSENT
CONFIRMED = EffectReconciliationOutcome.EFFECT_CONFIRMED


def _fences(recovered: RecoveredFixture) -> list[dict[str, Any]]:
    return recovered.gateway.inspect_task(recovered.task_id)["dispatch_fences"]


def _reconcile(recovered: RecoveredFixture, outcome, evidence, execution=None):
    row = execution or _execution_rows(recovered)[0]
    return EffectReconciler(recovered.db_path, clock=recovered.clock).reconcile(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        execution_id=row["execution_id"],
        action_id=row["action_id"],
        action_digest=row["action_digest"],
        outcome=outcome,
        evidence=evidence,
        reconciled_by="alec",
        reason="Inspected the target resource directly.",
    )


def _prove(recovered: RecoveredFixture, execution=None, fences: DispatchFences | None = None):
    row = execution or _execution_rows(recovered)[0]
    return (fences or recovered.gateway.dispatch_fences).prove_quiescent(
        task_id=recovered.task_id,
        execution_id=row["execution_id"],
        proven_by="alec",
        reason="Confirm no dispatch of step two can still land.",
    )


def _hold_lock(recovered: RecoveredFixture) -> DispatchLock:
    """Stand in for a hung process or orphaned child still holding the dispatch lock."""
    lock = recovered.gateway.dispatch_fences.lock_for(recovered.task_id, "action-step-two")
    assert lock.try_acquire()
    return lock


def _crash_after_effect(calls: list[dict[str, Any]], *, write: bool):
    def executor(action: dict[str, Any], root: Path | str | None) -> dict[str, Any]:
        calls.append(action)
        if len(calls) == 1:
            if write:
                (Path(root) / str(action["path"])).write_text(
                    str(action["content"]), encoding="utf-8"
                )
            raise SimulatedCrash()
        return execute_action(action, root)

    return executor


def _validate(recovered: RecoveredFixture, fence: dict[str, Any], **overrides: str):
    request = {
        "execution_id": fence["execution_id"],
        "task_id": fence["task_id"],
        "action_id": fence["action_id"],
        "idempotency_key": fence["idempotency_key"],
        "attempt_id": fence["attempt_id"],
    }
    request.update(overrides)
    with recovered.ledger._transaction() as connection:
        return DispatchFences.validate_crossing(connection, **request)


# --- the normal path -------------------------------------------------------------


def test_successful_dispatch_records_one_returned_fence(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))

    result = recovered.resume()
    [fence] = _fences(recovered)

    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert fence["state"] == "returned"
    assert fence["generation"] == 1
    assert fence["execution_id"] == _execution_rows(recovered)[0]["execution_id"]
    assert fence["attempt_id"] == recovered.attempt_id
    assert fence["crossing_at"] is not None and fence["returned_at"] is not None
    assert fence["outcome"]["result"]["success"] is True
    assert len(calls) == 1


# --- pre-dispatch safety -----------------------------------------------------------


def test_supersession_before_dispatch_never_crosses(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    holder: dict[str, RecoveredFixture] = {}

    def supersede(_proposal) -> None:
        holder["replacement"] = _replace_worker(holder["fixture"])

    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), before_execute_hook=supersede
    )
    holder["fixture"] = recovered

    result = recovered.resume()

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert _fences(recovered)[0]["state"] == "revoked"
    assert calls == []
    assert _step_two(recovered) == "not done\n"


def test_crash_before_dispatch_leaves_an_uncrossed_fence_that_is_revoked(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    armed = {"crash": True}

    def crash(_proposal) -> None:
        if armed["crash"]:
            raise SimulatedCrash()

    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), before_execute_hook=crash
    )
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    assert _fences(recovered)[0]["state"] == "issued"

    armed["crash"] = False
    replacement = _replace_worker(recovered)
    result = replacement.resume()

    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert _fences(replacement)[0]["state"] == "revoked"
    assert calls == []


def test_execution_without_a_fence_cannot_cross(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    holder: dict[str, RecoveredFixture] = {}

    def drop_fence(_proposal) -> None:
        with holder["fixture"].ledger._transaction() as connection:
            connection.execute("delete from ari_execution_dispatch_fences")

    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), before_execute_hook=drop_fence
    )
    holder["fixture"] = recovered

    result = recovered.resume()

    assert result.executed is False
    assert "No dispatch fence" in result.reason
    assert calls == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"action_id": "action-step-three"}, "different action"),
        ({"task_id": "task-other"}, "different action"),
        ({"idempotency_key": "recovered-action:other"}, "different digest"),
        ({"attempt_id": "attempt-other"}, "another attempt"),
        ({"execution_id": "action-execution-other"}, "No dispatch fence"),
    ],
)
def test_fence_from_wrong_action_execution_or_attempt_is_rejected(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    armed = {"crash": True}

    def crash(_proposal) -> None:
        if armed["crash"]:
            raise SimulatedCrash()

    recovered = _recovered_task(tmp_path, before_execute_hook=crash)
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    [fence] = _fences(recovered)

    assert _validate(recovered, fence)["fence_id"] == fence["fence_id"]
    with pytest.raises(DispatchFenceRejected, match=message):
        _validate(recovered, fence, **overrides)


def test_fence_crosses_at_most_once(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path)
    recovered.resume()
    [fence] = _fences(recovered)

    with pytest.raises(DispatchFenceRejected, match="at most once"):
        _validate(recovered, fence)


def test_old_generation_fence_after_plan_revision_is_rejected(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    armed = {"crash": True}

    def crash(_proposal) -> None:
        if armed["crash"]:
            raise SimulatedCrash()

    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), before_execute_hook=crash
    )
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    armed["crash"] = False
    replacement = _replace_worker(recovered)
    _revise_step_two(replacement, "revised content\n")

    revised = replacement.resume()
    old, new = _fences(replacement)

    assert revised.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert (old["generation"], new["generation"]) == (1, 2)
    assert old["state"] == "issued"  # the old worker never returned to revoke it
    with pytest.raises(DispatchFenceRejected, match="newer dispatch generation"):
        _validate(replacement, old)
    assert len(calls) == 1


# --- concurrency -----------------------------------------------------------------


def test_concurrent_dispatches_of_one_action_execute_once(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def run() -> None:
        gateway = RecoveredActionGateway(
            recovered.db_path,
            execution_root=recovered.root,
            clock=recovered.clock,
            pause_state_reader=lambda: {"paused": False, "reason": None},
            action_executor=_counting_executor(calls),
        )
        barrier.wait()
        results.append(
            gateway.resume_one(
                task_id=recovered.task_id,
                attempt_id=recovered.attempt_id,
                worker_identity=recovered.worker_identity,
                session_id=recovered.session_id,
            )
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(result.executed for result in results) == [False, True]
    assert len(calls) == 1
    assert [fence["state"] for fence in _fences(recovered)] == ["returned"]


def test_dispatch_lock_blocks_a_second_dispatch_even_if_governance_is_bypassed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense in depth: the lock alone prevents overlapping dispatches of one action."""
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    monkeypatch.setattr(RecoveredActionGateway, "_select_governing", lambda *a, **k: None)
    in_flight = _hold_lock(recovered)
    try:
        result = recovered.resume()
    finally:
        in_flight.release()

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert "dispatch lock" in result.reason
    assert _fences(recovered)[0]["state"] == "revoked"
    assert calls == []


# --- the effect boundary and in-flight dispatches --------------------------------


def test_supersession_after_crossing_cannot_stop_the_effect_but_blocks_redispatch(
    tmp_path: Path,
) -> None:
    """ARI cannot revoke an effect already past the boundary; it only prevents a second."""
    holder: dict[str, RecoveredFixture] = {}
    replacements: list[RecoveredFixture] = []
    calls: list[dict[str, Any]] = []

    def superseded_just_before_write(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        replacements.append(_replace_worker(holder["fixture"]))
        return execute_action(action, root)

    recovered = _recovered_task(tmp_path, action_executor=superseded_just_before_write)
    holder["fixture"] = recovered

    result = recovered.resume()
    replacement = replacements[0]

    assert result.executed is True
    assert result.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert _step_two(replacement) == "step two complete\n"  # the effect landed
    assert _fences(replacement)[0]["state"] == "returned"
    again = replacement.resume()
    assert again.executed is False
    assert len(calls) == 1


def test_new_action_is_refused_while_original_dispatch_is_in_flight(tmp_path: Path) -> None:
    """The reported double-effect sequence, end to end.

    While the superseded worker is still inside the effect, absence can be observed
    and recorded, but quiescence cannot be proven, so a revised action never starts.
    """
    holder: dict[str, RecoveredFixture] = {}
    observations: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def zombie(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        if len(calls) > 1:
            return execute_action(action, root)
        replacement = _replace_worker(holder["fixture"])
        observations["replacement"] = replacement
        observations["reconciled"] = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
        with pytest.raises(DispatchQuiescenceUnproven, match="in flight"):
            _prove(replacement)
        _revise_step_two(replacement, "new version while the old one is in flight\n")
        observations["second"] = replacement.resume()
        # Only now does the original operation land.
        return execute_action(action, root)

    recovered = _recovered_task(tmp_path, action_executor=zombie)
    holder["fixture"] = recovered
    recovered.resume()
    replacement = observations["replacement"]

    assert observations["reconciled"].transitioned is True
    assert observations["reconciled"].retry_eligible is False
    assert observations["second"].executed is False
    assert observations["second"].decision is ResumeDecision.DENY
    assert len(calls) == 1
    assert _step_two(replacement) == "step two complete\n"
    # The late report contradicts the absence, so the action is uncertain again.
    assert _execution_rows(replacement)[0]["state"] == "effect_may_have_occurred"
    assert replacement.resume().executed is False
    assert len(calls) == 1


def test_confirmed_absent_without_quiescence_stays_blocked_until_proven(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    assert _fences(replacement)[0]["state"] == "crossing"

    orphan = _hold_lock(replacement)  # e.g. an orphaned child still holding the lock
    try:
        reconciled = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
        _revise_step_two(replacement, "revised while unproven\n")
        blocked = replacement.resume()
        with pytest.raises(DispatchQuiescenceUnproven):
            _prove(replacement)
    finally:
        orphan.release()

    assert reconciled.retry_eligible is False
    assert _records_fence_state(replacement) == "crossing"
    assert blocked.executed is False
    assert blocked.idempotency_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    assert len(calls) == 1

    proof = _prove(replacement)
    retried = replacement.resume()

    assert (proof.previous_state, proof.state) == (
        DispatchFenceState.CROSSING,
        DispatchFenceState.QUIESCED,
    )
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2
    assert [fence["state"] for fence in _fences(replacement)] == ["quiesced", "returned"]


def _records_fence_state(recovered: RecoveredFixture) -> str | None:
    [record] = EffectReconciler(recovered.db_path).list_reconciliations(recovered.task_id)
    return record["dispatch_fence_state"]


def test_crash_immediately_after_effect_is_provably_quiescent_once_lock_is_free(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=True))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)

    first = _prove(replacement)
    second = _prove(replacement)
    confirmed = _reconcile(replacement, CONFIRMED, PRESENT_EVIDENCE)

    assert first.changed is True and first.state is DispatchFenceState.QUIESCED
    assert second.changed is False and second.state is DispatchFenceState.QUIESCED
    assert confirmed.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED
    assert replacement.resume().executed is False
    assert len(calls) == 1
    events = replacement.ledger.get_task_bundle(replacement.task_id)["events"]
    assert [event["event_type"] for event in events].count("action.dispatch_quiesced") == 1


def test_crash_before_result_persistence_still_records_the_returned_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def returns_without_effect(action: dict[str, Any], _root: Path | str | None):
        calls.append(action)
        return {"success": False, "path": str(action["path"])}

    recovered = _recovered_task(tmp_path, action_executor=returns_without_effect)

    def crash(*_args, **_kwargs):
        raise SimulatedCrash()

    monkeypatch.setattr(RecoveredActionGateway, "_persist_result", crash)
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    monkeypatch.undo()

    assert _execution_rows(recovered)[0]["state"] == "executing"
    assert _fences(recovered)[0]["state"] == "returned"
    replacement = _replace_worker(recovered)
    reconciled = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    assert reconciled.retry_eligible is True  # the call returned: no quiescence proof needed

    replacement.gateway.action_executor = _counting_executor(calls)
    _revise_step_two(replacement, "step two complete (retry)\n")
    retried = replacement.resume()
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2


def test_fencing_state_survives_restart(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)

    restarted = RecoveredActionGateway(
        recovered.db_path,
        execution_root=recovered.root,
        clock=recovered.clock,
        pause_state_reader=lambda: {"paused": False, "reason": None},
        action_executor=_counting_executor(calls),
    )
    [fence] = restarted.inspect_task(recovered.task_id)["dispatch_fences"]
    assert fence["state"] == "crossing"
    _revise_step_two(replacement, "after restart\n")
    assert replacement.resume().executed is False

    proof = _prove(replacement, fences=DispatchFences(recovered.db_path, clock=recovered.clock))
    assert proof.state is DispatchFenceState.QUIESCED
    after = restarted.resume_one(
        task_id=replacement.task_id,
        attempt_id=replacement.attempt_id,
        worker_identity=replacement.worker_identity,
        session_id=replacement.session_id,
    )
    assert after.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2


def test_quiescence_proof_requires_identity_and_an_existing_fence(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path)
    recovered.resume()
    row = _execution_rows(recovered)[0]
    fences = recovered.gateway.dispatch_fences

    with pytest.raises(ValueError, match="required"):
        fences.prove_quiescent(
            task_id=recovered.task_id, execution_id=row["execution_id"], proven_by=" ", reason="x"
        )
    with pytest.raises(DispatchQuiescenceUnproven, match="No dispatch fence"):
        fences.prove_quiescent(
            task_id="task-other", execution_id=row["execution_id"], proven_by="alec", reason="x"
        )


# --- subprocess effects ----------------------------------------------------------


def test_run_command_children_inherit_the_dispatch_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    root = ExecutionRoot(tmp_path)
    token = DISPATCH_HOLD_FDS.set((7,))
    try:
        root.run_command(["ls"])
    finally:
        DISPATCH_HOLD_FDS.reset(token)
    assert captured["pass_fds"] == (7,)

    root.run_command(["ls"])
    assert captured["pass_fds"] == ()


def test_orphaned_child_keeps_the_dispatch_lock_after_parent_releases(tmp_path: Path) -> None:
    """Models a killed parent: its descriptor closes, the inheriting child's stays open."""
    parent = DispatchLock(tmp_path / "action.lock")
    assert parent.try_acquire()
    assert parent.fd is not None
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
        pass_fds=(parent.fd,),
    )
    try:
        parent.release()
        assert DispatchLock(tmp_path / "action.lock").try_acquire() is False
    finally:
        assert child.stdin is not None
        child.stdin.close()
        child.wait(timeout=10)

    survivor = DispatchLock(tmp_path / "action.lock")
    assert survivor.try_acquire() is True
    survivor.release()
