from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ActionIdempotencyState,
    DispatchFences,
    DispatchFenceState,
    DispatchLandingUnproven,
    EffectReconciler,
    EffectReconciliationOutcome,
    EffectTerminality,
    ExecutionRoot,
    ReconciliationRefused,
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
INCONCLUSIVE = EffectReconciliationOutcome.INCONCLUSIVE
REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = REPO_ROOT / "services" / "ari-core" / "src"
MIGRATIONS = REPO_ROOT / "config" / "migrations"
WAIT_SECONDS = 20


def _fences(recovered: RecoveredFixture) -> list[dict[str, Any]]:
    return recovered.gateway.inspect_task(recovered.task_id)["dispatch_fences"]


def _reconcile(recovered: RecoveredFixture, outcome, evidence, execution=None, **extra):
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
        **extra,
    )


def _rule_out(recovered: RecoveredFixture, execution=None, fences: DispatchFences | None = None):
    row = execution or _execution_rows(recovered)[0]
    return (fences or recovered.gateway.dispatch_fences).rule_out_landing(
        task_id=recovered.task_id,
        execution_id=row["execution_id"],
        proven_by="alec",
        reason="Establish no dispatch of step two can still land.",
    )


def _hold_lock(recovered: RecoveredFixture) -> DispatchLock:
    """Stand in for a hung dispatcher still holding the dispatch lock."""
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


def _revise_step_two_action(recovered: RecoveredFixture, action: dict[str, Any]) -> None:
    """Record a canonical plan revision replacing step two's execution action."""
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    plan = dict(checkpoint["current_plan"])
    actions = [dict(item) for item in plan["actions"]]
    actions[1] = {**actions[1], "execution_action": action}
    plan["actions"] = actions
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(checkpoint, current_plan=plan),
    )


def _rename_step_two(recovered: RecoveredFixture, new_action_id: str) -> None:
    """Record a plan revision that gives step two's effect a different action_id."""
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    plan = dict(checkpoint["current_plan"])
    actions = [dict(item) for item in plan["actions"]]
    actions[1] = {**actions[1], "id": new_action_id}
    plan["actions"] = actions
    pending = [
        {**step, "action_id": new_action_id}
        if step.get("action_id") == "action-step-two"
        else step
        for step in checkpoint["pending_steps"]
    ]
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(
            checkpoint, current_plan=plan, pending_steps=pending
        ),
    )


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {path}")
        time.sleep(0.01)


def _child_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": os.pathsep.join([str(CORE_SRC), str(REPO_ROOT)])}


# --- the normal path -------------------------------------------------------------


def test_successful_in_process_dispatch_records_a_returned_fence_with_a_landing_token(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))

    result = recovered.resume()
    [fence] = _fences(recovered)

    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert fence["state"] == "returned"
    assert fence["effect_terminality"] == "in_process"
    assert fence["generation"] == 1
    assert fence["execution_id"] == _execution_rows(recovered)[0]["execution_id"]
    assert fence["attempt_id"] == recovered.attempt_id
    assert fence["crossing_at"] is not None and fence["returned_at"] is not None
    assert fence["landing_token"] is not None and fence["landing_ruled_out_at"] is not None
    assert fence["lock_inode"] is not None and Path(fence["lock_path"]).exists()
    assert fence["outcome"]["result"]["success"] is True
    assert len(calls) == 1


def test_injected_executor_is_unbounded_unless_it_declares_otherwise(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), effect_terminality=None
    )

    recovered.resume()
    [fence] = _fences(recovered)

    assert fence["state"] == "returned"
    assert fence["effect_terminality"] == "unbounded"
    assert fence["landing_token"] is None


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
    [fence] = _fences(recovered)

    assert result.executed is False
    assert result.idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    assert fence["state"] == "revoked"
    assert fence["landing_token"] is not None  # a fence that never crossed can never land
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


def test_failed_before_effect_stays_retryable_under_a_revision(tmp_path: Path) -> None:
    """The stricter model leaves the never-crossed path exactly as it was."""
    calls: list[dict[str, Any]] = []
    holder: dict[str, RecoveredFixture] = {}

    def supersede_once(_proposal) -> None:
        if "replacement" not in holder:
            holder["replacement"] = _replace_worker(holder["fixture"])

    recovered = _recovered_task(
        tmp_path, action_executor=_counting_executor(calls), before_execute_hook=supersede_once
    )
    holder["fixture"] = recovered
    assert recovered.resume().idempotency_state is ActionIdempotencyState.FAILED_BEFORE_EFFECT
    replacement = holder["replacement"]
    _revise_step_two(replacement, "step two complete (after stop)\n")

    retried = replacement.resume()

    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 1
    assert _step_two(replacement) == "step two complete (after stop)\n"


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


def test_crossing_is_refused_while_an_earlier_unbounded_dispatch_is_unproven(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense in depth: returned is not enough for an unbounded earlier dispatch."""
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(
        tmp_path,
        action_executor=_crash_after_effect(calls, write=False),
        effect_terminality=lambda _action: EffectTerminality.UNBOUNDED,
    )
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    with replacement.ledger._transaction() as connection:
        connection.execute("update ari_execution_dispatch_fences set state = 'returned'")
    monkeypatch.setattr(RecoveredActionGateway, "_select_governing", lambda *a, **k: None)
    replacement.gateway.action_executor = _counting_executor(calls)
    _revise_step_two(replacement, "governance bypassed\n")

    result = replacement.resume()

    assert result.executed is False
    assert "not been proven unable to land" in result.reason
    assert len(calls) == 1


# --- concurrency -----------------------------------------------------------------


def _resume_concurrently(recovered: RecoveredFixture, calls: list[dict[str, Any]]) -> list:
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def run() -> None:
        gateway = RecoveredActionGateway(
            recovered.db_path,
            execution_root=recovered.root,
            clock=recovered.clock,
            pause_state_reader=lambda: {"paused": False, "reason": None},
            action_executor=_counting_executor(calls),
            effect_terminality=recovered.gateway.effect_terminality,
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
    return results


def test_concurrent_dispatches_of_one_action_execute_once(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))

    results = _resume_concurrently(recovered, calls)

    assert sorted(result.executed for result in results) == [False, True]
    assert len(calls) == 1
    assert [fence["state"] for fence in _fences(recovered)] == ["returned"]


def test_concurrent_retries_after_safe_absence_execute_once(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    token = _rule_out(replacement).landing_token
    assert _reconcile(replacement, ABSENT, ABSENT_EVIDENCE, landing_token=token).redispatch_safe
    _revise_step_two(replacement, "step two complete (retry)\n")

    results = _resume_concurrently(replacement, calls)

    assert sorted(result.executed for result in results) == [False, True]
    assert len(calls) == 2  # the crashed original plus exactly one retry
    assert _step_two(replacement) == "step two complete (retry)\n"


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


# --- H1: absence observed before landing was ruled out ----------------------------


def test_absence_observed_while_crossing_never_qualifies_after_the_dispatch_ends(
    tmp_path: Path,
) -> None:
    """The H1 sequence in one process: stale absence, late effect, then terminality.

    Absence is truthfully observed while the superseded dispatch is still crossing.
    The effect lands afterwards and the dispatcher dies. Landing can then be ruled
    out, but the earlier absence must never make the revised action dispatchable.
    """
    holder: dict[str, RecoveredFixture] = {}
    observed: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def zombie(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        if len(calls) > 1:
            return execute_action(action, root)
        replacement = _replace_worker(holder["fixture"])
        observed["replacement"] = replacement
        observed["stale"] = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
        with pytest.raises(DispatchLandingUnproven, match="held"):
            _rule_out(replacement)
        execute_action(action, root)  # the effect lands after the absence observation
        raise SimulatedCrash()  # the dispatcher dies without recording a return

    recovered = _recovered_task(tmp_path, action_executor=zombie)
    holder["fixture"] = recovered
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = observed["replacement"]

    assert observed["stale"].transitioned is True
    assert observed["stale"].redispatch_safe is False
    assert _fences(replacement)[0]["state"] == "crossing"

    _revise_step_two(replacement, "step two complete (v2)\n")
    before_terminality = replacement.resume()
    proof = _rule_out(replacement)
    after_terminality = replacement.resume()

    assert (proof.previous_state, proof.state) == (
        DispatchFenceState.CROSSING,
        DispatchFenceState.LOCK_RELEASED,
    )
    for blocked in (before_terminality, after_terminality):
        assert blocked.executed is False
        assert blocked.idempotency_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
        assert "landing token" in blocked.reason
    [safety] = replacement.gateway.inspect_task(replacement.task_id)["redispatch_safety"]
    assert safety["landing_ruled_out"] is True
    assert safety["safe_to_redispatch"] is False  # the absence predates that proof
    assert len(calls) == 1
    assert _step_two(replacement) == "step two complete\n"

    # A post-landing observation finds the late effect and records it.
    confirmed = _reconcile(
        replacement, CONFIRMED, PRESENT_EVIDENCE, landing_token=proof.landing_token
    )
    assert confirmed.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED
    assert replacement.resume().executed is False
    assert len(calls) == 1


def test_post_landing_absence_makes_an_in_process_action_safe_to_redispatch(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)

    stale = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    _revise_step_two(replacement, "step two complete (retry)\n")
    assert stale.redispatch_safe is False
    assert replacement.resume().executed is False

    proof = _rule_out(replacement)  # obtained before the fresh observation
    fresh = _reconcile(
        replacement,
        ABSENT,
        [{**ABSENT_EVIDENCE[0], "summary": "Re-read after landing was ruled out."}],
        landing_token=proof.landing_token,
    )
    retried = replacement.resume()

    assert fresh.redispatch_safe is True
    assert fresh.previous_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    [original, retry] = replacement.gateway.inspect_task(replacement.task_id)[
        "redispatch_safety"
    ]
    assert original["landing_ruled_out"] is True
    assert original["safe_to_redispatch"] is True
    assert retry["state"] == "succeeded"
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2
    assert [fence["state"] for fence in _fences(replacement)] == ["lock_released", "returned"]
    events = replacement.ledger.get_task_bundle(replacement.task_id)["events"]
    kinds = [event["event_type"] for event in events]
    assert kinds.count("action.dispatch_landing_ruled_out") == 1


def test_returned_in_process_dispatch_needs_a_bound_observation_too(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A synchronous file action that returned can be ruled out, but absence must follow."""
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
    replacement.gateway.action_executor = _counting_executor(calls)
    _revise_step_two(replacement, "step two complete (retry)\n")

    unbound = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    assert unbound.redispatch_safe is False
    assert replacement.resume().executed is False

    proof = _rule_out(replacement)
    assert proof.changed is False and proof.state is DispatchFenceState.RETURNED
    bound = _reconcile(
        replacement,
        ABSENT,
        [{**ABSENT_EVIDENCE[0], "summary": "Re-read after the return."}],
        landing_token=proof.landing_token,
    )
    retried = replacement.resume()

    assert bound.redispatch_safe is True
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2


def test_landing_token_must_belong_to_the_execution(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)

    with pytest.raises(ReconciliationRefused, match="landing token"):
        _reconcile(replacement, ABSENT, ABSENT_EVIDENCE, landing_token="landing-forged")
    with pytest.raises(ReconciliationRefused, match="non-empty"):
        _reconcile(replacement, ABSENT, ABSENT_EVIDENCE, landing_token=" ")
    assert EffectReconciler(replacement.db_path).list_reconciliations(replacement.task_id) == []


def test_observation_timestamped_before_landing_was_ruled_out_is_inconclusive(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    proof = _rule_out(replacement)

    early = _reconcile(
        replacement,
        ABSENT,
        [{**ABSENT_EVIDENCE[0], "observed_at": "2026-10-01T12:00:00Z"}],
        landing_token=proof.landing_token,
    )

    assert early.outcome is INCONCLUSIVE
    assert early.redispatch_safe is False
    assert "before landing was ruled out" in early.assessment
    _revise_step_two(replacement, "step two complete (retry)\n")
    assert replacement.resume().executed is False
    assert len(calls) == 1


def test_landing_cannot_be_ruled_out_while_the_dispatch_lock_is_held(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)

    hung = _hold_lock(replacement)  # e.g. a stopped dispatcher process
    try:
        with pytest.raises(DispatchLandingUnproven, match="held"):
            _rule_out(replacement)
    finally:
        hung.release()

    assert _fences(replacement)[0]["state"] == "crossing"
    first = _rule_out(replacement)
    second = _rule_out(replacement)
    assert first.changed is True and first.state is DispatchFenceState.LOCK_RELEASED
    assert second.changed is False and second.landing_token == first.landing_token


def test_redispatch_safety_state_survives_restart(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    proof = _rule_out(replacement, fences=DispatchFences(recovered.db_path, clock=recovered.clock))
    _revise_step_two(replacement, "after restart\n")

    def restarted() -> RecoveredActionGateway:
        return RecoveredActionGateway(
            recovered.db_path,
            execution_root=recovered.root,
            clock=recovered.clock,
            pause_state_reader=lambda: {"paused": False, "reason": None},
            action_executor=_counting_executor(calls),
            effect_terminality=recovered.gateway.effect_terminality,
        )

    def resume(gateway: RecoveredActionGateway):
        return gateway.resume_one(
            task_id=replacement.task_id,
            attempt_id=replacement.attempt_id,
            worker_identity=replacement.worker_identity,
            session_id=replacement.session_id,
        )

    [fence] = restarted().inspect_task(recovered.task_id)["dispatch_fences"]
    assert fence["state"] == "lock_released"
    assert resume(restarted()).executed is False  # the stale absence still governs

    EffectReconciler(recovered.db_path, clock=recovered.clock).reconcile(
        task_id=replacement.task_id,
        attempt_id=replacement.attempt_id,
        execution_id=fence["execution_id"],
        action_id=fence["action_id"],
        action_digest=_execution_rows(replacement)[0]["action_digest"],
        outcome=ABSENT,
        evidence=[{**ABSENT_EVIDENCE[0], "summary": "Re-read after restart."}],
        reconciled_by="alec",
        reason="Fresh observation after landing was ruled out.",
        landing_token=proof.landing_token,
    )
    after = resume(restarted())
    assert after.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2


def test_landing_proof_requires_identity_and_an_existing_fence(tmp_path: Path) -> None:
    recovered = _recovered_task(tmp_path)
    recovered.resume()
    row = _execution_rows(recovered)[0]
    fences = recovered.gateway.dispatch_fences

    with pytest.raises(ValueError, match="required"):
        fences.rule_out_landing(
            task_id=recovered.task_id, execution_id=row["execution_id"], proven_by=" ", reason="x"
        )
    with pytest.raises(DispatchLandingUnproven, match="No dispatch fence"):
        fences.rule_out_landing(
            task_id="task-other", execution_id=row["execution_id"], proven_by="alec", reason="x"
        )


# --- H1 with a real process and SIGKILL -------------------------------------------

_SIGKILLED_DISPATCHER = textwrap.dedent(
    """
    import json, os, signal, sys, time
    from datetime import datetime
    from pathlib import Path
    from ari_core.modules.execution import (
        RecoveredActionGateway, classify_effect_terminality, execute_action,
    )

    config = json.loads(sys.argv[1])
    control = Path(config["control"])

    def executor(action, root):
        (control / "crossed").write_text(str(os.getpid()))
        while not (control / "go").exists():
            time.sleep(0.01)
        if config["land"]:
            with open(control / "effects.log", "a") as log:
                log.write("original\\n")
            execute_action(action, root)
        os.kill(os.getpid(), signal.SIGKILL)

    now = datetime.fromisoformat(config["now"])
    RecoveredActionGateway(
        Path(config["db"]),
        execution_root=config["root"],
        clock=lambda: now,
        pause_state_reader=lambda: {"paused": False, "reason": None},
        action_executor=executor,
        effect_terminality=classify_effect_terminality,
    ).resume_one(
        task_id=config["task_id"],
        attempt_id=config["attempt_id"],
        worker_identity=config["worker_identity"],
        session_id=config["session_id"],
    )
    """
)


def _spawn_sigkilled_dispatcher(
    tmp_path: Path, recovered: RecoveredFixture, *, land: bool
) -> tuple[subprocess.Popen[bytes], Path]:
    control = tmp_path / "control"
    control.mkdir()
    script = tmp_path / "dispatcher.py"
    script.write_text(_SIGKILLED_DISPATCHER, encoding="utf-8")
    config = {
        "control": str(control),
        "land": land,
        "db": str(recovered.db_path),
        "root": str(recovered.root),
        "now": recovered.clock().isoformat(),
        "task_id": recovered.task_id,
        "attempt_id": recovered.attempt_id,
        "worker_identity": recovered.worker_identity,
        "session_id": recovered.session_id,
    }
    child = subprocess.Popen(
        [sys.executable, str(script), json.dumps(config)], env=_child_env()
    )
    _wait_for(control / "crossed")
    return child, control


def _effects(control: Path, calls: list[dict[str, Any]]) -> int:
    log = control / "effects.log"
    landed = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    return landed + len(calls)


def test_sigkilled_dispatcher_with_stale_absence_never_duplicates_the_effect(
    tmp_path: Path,
) -> None:
    """The audited H1 reproduction: it produced two effects before this repair."""
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    child, control = _spawn_sigkilled_dispatcher(tmp_path, recovered, land=True)
    try:
        replacement = _replace_worker(recovered)
        stale = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)  # true at this moment
        (control / "go").write_text("go")
        assert child.wait(timeout=WAIT_SECONDS) == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()

    proof = _rule_out(replacement)  # the SIGKILL released the dispatcher's lock
    _revise_step_two(replacement, "step two complete (v2)\n")
    blocked = replacement.resume()

    assert stale.redispatch_safe is False
    assert proof.state is DispatchFenceState.LOCK_RELEASED
    assert blocked.executed is False
    assert _effects(control, calls) == 1
    assert _step_two(replacement) == "step two complete\n"

    found = _reconcile(
        replacement, CONFIRMED, PRESENT_EVIDENCE, landing_token=proof.landing_token
    )
    assert found.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED
    assert replacement.resume().executed is False
    assert _effects(control, calls) == 1


def test_sigkilled_dispatcher_that_never_landed_can_be_retried_after_bound_absence(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_counting_executor(calls))
    child, control = _spawn_sigkilled_dispatcher(tmp_path, recovered, land=False)
    try:
        replacement = _replace_worker(recovered)
        with pytest.raises(DispatchLandingUnproven, match="held"):
            _rule_out(replacement)  # the dispatcher is alive and inside the effect
        (control / "go").write_text("go")
        assert child.wait(timeout=WAIT_SECONDS) == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()

    proof = _rule_out(replacement)
    bound = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE, landing_token=proof.landing_token)
    _revise_step_two(replacement, "step two complete (retry)\n")
    retried = replacement.resume()

    assert bound.redispatch_safe is True
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert _effects(control, calls) == 1
    assert _step_two(replacement) == "step two complete (retry)\n"


# --- H3: subprocess effects and escaped descendants -------------------------------


def _escaping_command(effect: Path, release: Path, *, exit_code: int) -> list[str]:
    """A direct child that starts a detached grandchild which does not keep the lock."""
    grandchild = textwrap.dedent(
        f"""
        import sys, time
        from pathlib import Path
        deadline = time.monotonic() + 60  # never outlive a failed test for long
        while not Path({str(release)!r}).exists():
            if time.monotonic() > deadline:
                sys.exit(1)
            time.sleep(0.01)
        with open({str(effect)!r}, "a") as log:
            log.write("grandchild effect\\n")
        """
    )
    child = textwrap.dedent(
        f"""
        import subprocess, sys
        subprocess.Popen(
            [sys.executable, "-c", {grandchild!r}],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        sys.exit({exit_code})
        """
    )
    return [sys.executable, "-c", child]


@pytest.fixture
def python_is_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ExecutionRoot, "ALLOWED_COMMANDS", {*ExecutionRoot.ALLOWED_COMMANDS, sys.executable}
    )


def _command_task(tmp_path: Path, command: list[str], **kwargs: Any) -> RecoveredFixture:
    return _recovered_task(
        tmp_path,
        step_two_action=("run_command", {"command": command}),
        permitted_side_effects=("write_file", "run_command"),
        **kwargs,
    )


def _wait_for_text(path: Path, text: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not (path.exists() and text in path.read_text(encoding="utf-8")):
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {text!r} in {path}")
        time.sleep(0.01)


def test_escaped_grandchild_lands_after_run_command_returned_and_lock_was_free(
    tmp_path: Path,
    python_is_allowlisted: None,
) -> None:
    effect = tmp_path / "effects.log"
    release = tmp_path / "release"
    recovered = _command_task(tmp_path, _escaping_command(effect, release, exit_code=1))

    first = recovered.resume()  # the real executor and real subprocess.run
    [fence] = _fences(recovered)
    lock = recovered.gateway.dispatch_fences.lock_for(recovered.task_id, "action-step-two")
    lock_free = lock.try_acquire()
    lock.release()

    # Under the old semantics every signal said "nothing can land": the call returned
    # and the lock is free. The grandchild has not acted yet.
    assert first.idempotency_state is ActionIdempotencyState.VERIFICATION_FAILED
    assert fence["state"] == "returned" and fence["effect_terminality"] == "unbounded"
    assert fence["landing_token"] is None
    assert lock_free is True
    assert not effect.exists()

    with pytest.raises(DispatchLandingUnproven, match="unbounded"):
        _rule_out(recovered)
    absent_now = _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)  # truthful at this instant
    _revise_step_two_action(
        recovered, {"type": "run_command", "command": [sys.executable, "-c", "pass"]}
    )
    blocked = recovered.resume()

    assert absent_now.redispatch_safe is False
    assert blocked.executed is False

    release.write_text("go")
    _wait_for_text(effect, "grandchild effect")  # the effect lands after everything above
    found = _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)
    assert found.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED


def test_injected_executor_whose_descendant_lands_later_stays_blocked(tmp_path: Path) -> None:
    effect = tmp_path / "effects.log"
    release = tmp_path / "release"
    calls: list[dict[str, Any]] = []

    def spawns_and_fails(action: dict[str, Any], _root: Path | str | None):
        calls.append(action)
        subprocess.Popen(
            _escaping_command(effect, release, exit_code=0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).wait(timeout=WAIT_SECONDS)
        raise RuntimeError("connection reset after dispatch")

    recovered = _recovered_task(tmp_path, action_executor=spawns_and_fails, effect_terminality=None)
    first = recovered.resume()

    assert first.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert _fences(recovered)[0]["state"] == "returned"
    with pytest.raises(DispatchLandingUnproven, match="unbounded"):
        _rule_out(recovered)
    _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    _revise_step_two(recovered, "step two complete (v2)\n")
    assert recovered.resume().executed is False

    release.write_text("go")
    _wait_for_text(effect, "grandchild effect")
    assert recovered.resume().executed is False
    assert len(calls) == 1


def test_run_command_is_never_safe_to_redispatch_once_crossed(
    tmp_path: Path,
    python_is_allowlisted: None,
) -> None:
    recovered = _command_task(tmp_path, [sys.executable, "-c", "import sys; sys.exit(3)"])
    first = recovered.resume()
    assert first.idempotency_state is ActionIdempotencyState.VERIFICATION_FAILED

    with pytest.raises(DispatchLandingUnproven, match="unbounded"):
        _rule_out(recovered)
    absent = _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    with pytest.raises(ReconciliationRefused, match="landing token"):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE, landing_token="landing-guess")
    _revise_step_two_action(
        recovered, {"type": "run_command", "command": [sys.executable, "-c", "pass"]}
    )
    revised = recovered.resume()
    _rename_step_two(recovered, "action-step-two-renamed")
    renamed = recovered.resume()

    assert absent.redispatch_safe is False
    assert revised.executed is False
    assert renamed.executed is False
    assert "action-step-two in this task is unresolved" in renamed.reason
    assert len(_fences(recovered)) == 1


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


# --- renamed actions ------------------------------------------------------------


def test_renamed_action_is_refused_while_the_original_dispatch_is_in_flight(
    tmp_path: Path,
) -> None:
    """Before this repair, renaming the action dispatched it a second time."""
    holder: dict[str, RecoveredFixture] = {}
    observed: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def zombie(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        if len(calls) > 1:
            return execute_action(action, root)
        replacement = _replace_worker(holder["fixture"])
        _rename_step_two(replacement, "action-step-two-renamed")
        observed["replacement"] = replacement
        observed["renamed"] = replacement.resume()
        return execute_action(action, root)

    recovered = _recovered_task(tmp_path, action_executor=zombie)
    holder["fixture"] = recovered
    recovered.resume()
    replacement = observed["replacement"]

    assert observed["renamed"].executed is False
    assert observed["renamed"].decision is ResumeDecision.DENY
    assert "action-step-two in this task is unresolved" in observed["renamed"].reason
    assert len(calls) == 1
    assert replacement.resume().executed is False
    assert len(calls) == 1


def test_renamed_action_is_refused_after_a_stale_absence(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=True))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    _rule_out(replacement)
    _rename_step_two(replacement, "action-step-two-renamed")

    renamed = replacement.resume()

    assert renamed.executed is False
    assert len(calls) == 1


def test_renamed_action_may_run_once_the_original_is_safe_to_redispatch(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    token = _rule_out(replacement).landing_token
    _reconcile(replacement, ABSENT, ABSENT_EVIDENCE, landing_token=token)
    _rename_step_two(replacement, "action-step-two-renamed")

    renamed = replacement.resume()

    assert renamed.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2


# --- H5: lock identity ----------------------------------------------------------


def _crossed_and_abandoned(tmp_path: Path) -> RecoveredFixture:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(tmp_path, action_executor=_crash_after_effect(calls, write=False))
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    replacement = _replace_worker(recovered)
    assert _fences(replacement)[0]["state"] == "crossing"
    return replacement


def test_unlinked_and_recreated_lock_file_cannot_prove_landing(tmp_path: Path) -> None:
    replacement = _crossed_and_abandoned(tmp_path)
    [fence] = _fences(replacement)
    lock_path = Path(fence["lock_path"])
    original = DispatchLock(lock_path)
    assert original.try_acquire()  # stands in for the dispatcher still holding its lock
    try:
        lock_path.unlink()
        with pytest.raises(DispatchLandingUnproven, match="no longer exists"):
            _rule_out(replacement)

        # Recreating the path yields a new inode that anyone can lock.
        imposter = DispatchLock(lock_path)
        assert imposter.try_acquire() is True
        imposter.release()
        with pytest.raises(DispatchLandingUnproven, match="not the one the dispatcher held"):
            _rule_out(replacement)
    finally:
        original.release()

    # Even once the original holder is gone, the recorded inode cannot be re-proven.
    with pytest.raises(DispatchLandingUnproven, match="not the one the dispatcher held"):
        _rule_out(replacement)
    assert _fences(replacement)[0]["state"] == "crossing"


def test_removed_and_recreated_lock_directory_cannot_prove_landing(tmp_path: Path) -> None:
    replacement = _crossed_and_abandoned(tmp_path)
    lock_path = Path(_fences(replacement)[0]["lock_path"])
    lock_path.unlink()
    lock_path.parent.rmdir()

    with pytest.raises(DispatchLandingUnproven, match="no longer exists"):
        _rule_out(replacement)
    lock_path.parent.mkdir()
    lock_path.touch()
    with pytest.raises(DispatchLandingUnproven, match="not the one the dispatcher held"):
        _rule_out(replacement)


def test_lock_on_an_unlinked_inode_is_refused_at_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the file is replaced between open and flock, the lock excludes nobody."""
    path = tmp_path / "action.lock"
    real_flock = __import__("fcntl").flock

    def flock_then_replace(fd: int, operation: int) -> None:
        real_flock(fd, operation)
        path.unlink()
        path.touch()

    monkeypatch.setattr("ari_core.modules.execution.dispatch.fcntl.flock", flock_then_replace)
    lock = DispatchLock(path)

    assert lock.try_acquire() is False
    assert lock.refusal is not None and "replaced" in lock.refusal
    assert lock.fd is None


def test_database_path_aliases_share_one_lock(tmp_path: Path) -> None:
    real = tmp_path / "state"
    real.mkdir()
    (tmp_path / "linked").symlink_to(real, target_is_directory=True)
    (real / "ari.db").touch()
    (tmp_path / "file-link.db").symlink_to(real / "ari.db")
    aliases = [
        real / "ari.db",
        tmp_path / "linked" / "ari.db",
        tmp_path / "state" / ".." / "state" / "ari.db",
        tmp_path / "file-link.db",
    ]

    paths = {DispatchFences(alias).lock_for("task", "action").path for alias in aliases}

    assert paths == {(real / "dispatch-locks" / f"{DispatchFences.lock_key('task', 'action')}.lock").resolve()}


def test_hard_linked_database_alias_proves_against_the_recorded_lock(tmp_path: Path) -> None:
    """A hard link derives another lock directory; proofs still use the recorded inode."""
    replacement = _crossed_and_abandoned(tmp_path)
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    os.link(replacement.db_path, alias_dir / "ari.db")
    via_alias = DispatchFences(alias_dir / "ari.db", clock=replacement.clock)
    holder = DispatchLock(Path(_fences(replacement)[0]["lock_path"]))
    assert holder.try_acquire()
    try:
        assert via_alias.lock_for(replacement.task_id, "action-step-two").path.parent != (
            replacement.gateway.dispatch_fences.lock_dir
        )
        with pytest.raises(DispatchLandingUnproven, match="held"):
            _rule_out(replacement, fences=via_alias)
    finally:
        holder.release()
    assert _rule_out(replacement, fences=via_alias).state is DispatchFenceState.LOCK_RELEASED


# --- migration --------------------------------------------------------------------


def test_migration_revokes_legacy_retry_eligibility_and_renames_quiesced(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "legacy.db")
    connection.execute(
        "create table ari_execution_action_executions (execution_id text primary key)"
    )
    for name in ("0004_effect_reconciliation.sql", "0005_dispatch_fences.sql"):
        connection.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
    fence_columns = (
        "fence_id, execution_id, task_id, action_id, idempotency_key, attempt_id, "
        "generation, lock_key, state, issued_at"
    )
    connection.executemany(
        f"insert into ari_execution_dispatch_fences ({fence_columns}, quiesced_at) "
        "values (?, ?, 't', 'a', 'k', 'at', ?, 'lk', ?, 'now', ?)",
        [
            ("f-quiesced", "e-1", 1, "quiesced", "then"),
            ("f-revoked", "e-2", 2, "revoked", None),
        ],
    )
    connection.execute(
        """
        insert into ari_execution_effect_reconciliations (
            reconciliation_id, request_key, execution_id, task_id, attempt_id,
            reserving_attempt_id, decision_id, action_id, action_digest, idempotency_key,
            requested_outcome, outcome, previous_state, effective_previous_state,
            resulting_state, retry_eligible, reconciled_by, reason, assessment,
            evidence_json, evidence_sha256, basis_checkpoint_id, provenance_json,
            created_at, dispatch_fence_state
        ) values ('r-1', 'rk', 'e-1', 't', 'at', 'at', 'd', 'a', 'dg', 'k',
            'effect_confirmed_absent', 'effect_confirmed_absent', 'executing',
            'effect_may_have_occurred', 'effect_confirmed_absent', 1, 'alec', 'r', 'a',
            '[]', 'sha', 'cp', '{}', 'now', 'quiesced')
        """
    )
    connection.commit()

    connection.executescript((MIGRATIONS / "0006_redispatch_safety.sql").read_text("utf-8"))
    connection.row_factory = sqlite3.Row
    fences = {
        row["fence_id"]: row
        for row in connection.execute("select * from ari_execution_dispatch_fences")
    }
    record = connection.execute("select * from ari_execution_effect_reconciliations").fetchone()

    assert fences["f-quiesced"]["state"] == "lock_released"
    assert fences["f-quiesced"]["lock_released_at"] == "then"
    assert fences["f-quiesced"]["landing_token"] is None  # legacy: never proven
    assert fences["f-quiesced"]["effect_terminality"] is None
    assert fences["f-revoked"]["landing_token"] is not None
    assert record["redispatch_safe"] == 0
    assert record["landing_token"] is None
    connection.close()
