from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from ari_core.modules.execution import (
    ActionIdempotencyState,
    EffectReconciler,
    EffectReconciliationOutcome,
    ExecutionLedger,
    ReconciliationRefused,
    RecoveredActionGateway,
    ResumeDecision,
    TaskLifecycleState,
)
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

CONFIRMED = EffectReconciliationOutcome.EFFECT_CONFIRMED
ABSENT = EffectReconciliationOutcome.EFFECT_CONFIRMED_ABSENT
INCONCLUSIVE = EffectReconciliationOutcome.INCONCLUSIVE

PRESENT_EVIDENCE = [
    {
        "kind": "filesystem_observation",
        "summary": "step-two.txt holds the intended content.",
        "indicates": "effect_present",
        "reference": "file:step-two.txt#sha256:intended",
    }
]
ABSENT_EVIDENCE = [
    {
        "kind": "filesystem_observation",
        "summary": "step-two.txt is unchanged since before dispatch.",
        "indicates": "effect_absent",
        "reference": "file:step-two.txt#sha256:original",
    }
]


def _dispatching_executor(calls: list[dict[str, Any]], *, write: bool):
    """Fail after dispatch, optionally after the side effect really happened."""

    def executor(action: dict[str, Any], root: Path | str | None) -> dict[str, Any]:
        calls.append(action)
        if len(calls) == 1:
            if write:
                (Path(root) / str(action["path"])).write_text(
                    str(action["content"]), encoding="utf-8"
                )
            raise RuntimeError("connection reset after dispatch")
        from ari_core.modules.execution import execute_action

        return execute_action(action, root)

    return executor


def _uncertain(tmp_path: Path, *, write: bool, **kwargs: Any) -> tuple[RecoveredFixture, list]:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(
        tmp_path, action_executor=_dispatching_executor(calls, write=write), **kwargs
    )
    first = recovered.resume()
    assert first.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    return recovered, calls


def _reconcile(
    recovered: RecoveredFixture,
    outcome: EffectReconciliationOutcome | str,
    evidence: Any,
    *,
    execution: dict[str, Any] | None = None,
    reconciler: EffectReconciler | None = None,
    **overrides: Any,
):
    row = execution or _execution_rows(recovered)[-1]
    request: dict[str, Any] = {
        "task_id": recovered.task_id,
        "attempt_id": recovered.attempt_id,
        "execution_id": row["execution_id"],
        "action_id": row["action_id"],
        "action_digest": row["action_digest"],
        "outcome": outcome,
        "evidence": evidence,
        "reconciled_by": "alec",
        "reason": "Inspected the target resource directly.",
    }
    request.update(overrides)
    return (reconciler or EffectReconciler(recovered.db_path, clock=recovered.clock)).reconcile(
        **request
    )


def _records(recovered: RecoveredFixture) -> list[dict[str, Any]]:
    return EffectReconciler(recovered.db_path).list_reconciliations(recovered.task_id)


def _events(recovered: RecoveredFixture, event_type: str) -> list[dict[str, Any]]:
    bundle = recovered.ledger.get_task_bundle(recovered.task_id)
    assert bundle is not None
    return [event for event in bundle["events"] if event["event_type"] == event_type]


def _snapshot(recovered: RecoveredFixture) -> tuple[Any, ...]:
    bundle = recovered.ledger.get_task_bundle(recovered.task_id)
    assert bundle is not None
    return (
        _execution_rows(recovered),
        _records(recovered),
        len(bundle["events"]),
        len(bundle["checkpoints"]),
        bundle["task"]["latest_checkpoint_id"],
    )


def test_confirmed_effect_completes_step_and_is_never_redispatched(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=True, steps=3)

    result = _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)
    row = _execution_rows(recovered)[0]
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)

    assert result.transitioned is True
    assert result.previous_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert result.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED
    assert result.retry_eligible is False
    assert result.checkpoint_id == latest["checkpoint_id"]
    assert row["state"] == "effect_confirmed"
    assert row["reconciliation_id"] == result.reconciliation_id
    assert [step["action_id"] for step in latest["pending_steps"]] == ["action-step-three"]
    reconciled_step = latest["completed_steps"][-1]
    assert reconciled_step["action_id"] == "action-step-two"
    assert reconciled_step["reconciled"] is True
    assert reconciled_step["verified"] is False

    # Control proceeds to the next action; the confirmed action never runs again.
    following = recovered.resume()
    assert following.proposal.action_id == "action-step-three"
    assert following.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert [action["path"] for action in calls] == ["step-two.txt", "step-three.txt"]


def test_confirmed_effect_cannot_be_reopened_by_plan_revision(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=True)
    _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)

    # A revision that puts the action back in pending under a new digest is still denied.
    checkpoint = recovered.gateway._latest_checkpoint(recovered.task_id)
    recovered.ledger.record_boundary(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        trigger="plan_revised",
        event_type="plan.revised",
        state=RecoveredActionGateway._checkpoint_state(
            checkpoint,
            pending_steps=[{"action_id": "action-step-two", "action_type": "write_file"}],
        ),
    )
    _revise_step_two(recovered, "reopened after confirmation\n")
    retry = recovered.resume()

    assert retry.executed is False
    assert retry.decision is ResumeDecision.DENY
    assert retry.idempotency_state in {
        ActionIdempotencyState.EFFECT_CONFIRMED,
        ActionIdempotencyState.ALREADY_COMPLETED,
    }
    assert len(calls) == 1
    assert _step_two(recovered) == "step two complete\n"


def test_confirmed_absent_marks_retry_eligible_without_dispatching(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=False)

    result = _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)

    assert result.transitioned is True
    assert result.resulting_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    assert result.retry_eligible is True
    assert len(calls) == 1  # reconciliation itself never dispatches
    assert _step_two(recovered) == "not done\n"
    assert [step["action_id"] for step in latest["pending_steps"]] == ["action-step-two"]
    assert "plan revision" in str(latest["next_recommended_action"])

    # The same reserved action is still never re-dispatched automatically.
    same_digest = recovered.resume()
    assert same_digest.executed is False
    assert same_digest.idempotency_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    assert len(calls) == 1

    # Only a separately authorized canonical plan revision may run it again.
    _revise_step_two(recovered, "step two complete (retry)\n")
    retried = recovered.resume()
    assert retried.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert len(calls) == 2
    assert _step_two(recovered) == "step two complete (retry)\n"


def test_confirmed_absent_retry_still_requires_action_bound_approval(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    recovered = _recovered_task(
        tmp_path,
        approval_required=True,
        action_executor=_dispatching_executor(calls, write=False),
    )
    recovered.gateway.approve_next_action(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        approved_by="alec",
        reason="Approve step two once.",
    )
    assert recovered.resume().idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    _revise_step_two(recovered, "step two complete (retry)\n")

    retry = recovered.resume()

    assert retry.executed is False
    assert retry.decision is ResumeDecision.REQUIRE_APPROVAL
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("outcome", "evidence", "assessment"),
    [
        (
            CONFIRMED,
            [{"kind": "log", "summary": "No record either way.", "indicates": "inconclusive"}],
            "Insufficient evidence",
        ),
        (CONFIRMED, [*PRESENT_EVIDENCE, *ABSENT_EVIDENCE], "contradictory"),
        (ABSENT, [*ABSENT_EVIDENCE, *PRESENT_EVIDENCE], "contradictory"),
        (
            ABSENT,
            [{"kind": "operator", "summary": "Looks unchanged.", "indicates": "effect_absent"}],
            "verifiable reference",
        ),
        (
            ABSENT,
            [
                *ABSENT_EVIDENCE,
                {"kind": "log", "summary": "Log was rotated.", "indicates": "inconclusive"},
            ],
            "not every observation",
        ),
        (INCONCLUSIVE, PRESENT_EVIDENCE, "requester's direction"),
    ],
)
def test_insufficient_or_contradictory_evidence_remains_uncertain(
    tmp_path: Path,
    outcome: EffectReconciliationOutcome,
    evidence: list[dict[str, Any]],
    assessment: str,
) -> None:
    recovered, calls = _uncertain(tmp_path, write=False)
    checkpoint_before = recovered.gateway._latest_checkpoint(recovered.task_id)

    result = _reconcile(recovered, outcome, evidence)

    assert result.outcome is INCONCLUSIVE
    assert result.requested_outcome is outcome
    assert result.transitioned is False
    assert result.retry_eligible is False
    assert result.checkpoint_id is None
    assert assessment in result.assessment
    assert _execution_rows(recovered)[0]["state"] == "effect_may_have_occurred"
    assert (
        recovered.gateway._latest_checkpoint(recovered.task_id)["checkpoint_id"]
        == checkpoint_before["checkpoint_id"]
    )
    record = _records(recovered)[0]
    assert record["outcome"] == "inconclusive"
    assert record["evidence"][0]["kind"] == evidence[0]["kind"]
    assert len(_events(recovered, "action.effect_reconciliation_inconclusive")) == 1

    blocked = recovered.resume()
    assert blocked.executed is False
    assert blocked.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert len(calls) == 1

    # Inconclusive evidence does not foreclose a later, sufficient reconciliation.
    assert _reconcile(recovered, ABSENT, ABSENT_EVIDENCE).transitioned is True


def test_duplicate_identical_request_is_idempotent(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=True)

    first = _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)
    snapshot = _snapshot(recovered)
    second = _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.reconciliation_id == first.reconciliation_id
    assert second.checkpoint_id == first.checkpoint_id
    assert _snapshot(recovered) == snapshot
    assert len(_events(recovered, "action.effect_reconciled")) == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("second_outcome", "second_evidence"),
    [
        (ABSENT, ABSENT_EVIDENCE),
        (CONFIRMED, [{**PRESENT_EVIDENCE[0], "summary": "Different observation."}]),
        (INCONCLUSIVE, PRESENT_EVIDENCE),
    ],
)
def test_second_reconciliation_after_transition_is_refused(
    tmp_path: Path,
    second_outcome: EffectReconciliationOutcome,
    second_evidence: list[dict[str, Any]],
) -> None:
    recovered, calls = _uncertain(tmp_path, write=True)
    first = _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE)
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match="not eligible"):
        _reconcile(recovered, second_outcome, second_evidence)

    assert _snapshot(recovered) == snapshot
    assert _execution_rows(recovered)[0]["reconciliation_id"] == first.reconciliation_id
    assert len(calls) == 1


def test_concurrent_conflicting_reconciliations_apply_exactly_one(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=False)
    barrier = threading.Barrier(2)
    outcomes: dict[str, Any] = {}

    def run(name: str, outcome: EffectReconciliationOutcome, evidence: Any) -> None:
        reconciler = EffectReconciler(recovered.db_path, clock=recovered.clock)
        barrier.wait()
        try:
            outcomes[name] = _reconcile(recovered, outcome, evidence, reconciler=reconciler)
        except ReconciliationRefused as error:
            outcomes[name] = error

    threads = [
        threading.Thread(target=run, args=("confirm", CONFIRMED, PRESENT_EVIDENCE)),
        threading.Thread(target=run, args=("absent", ABSENT, ABSENT_EVIDENCE)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    applied = [value for value in outcomes.values() if not isinstance(value, Exception)]
    refused = [value for value in outcomes.values() if isinstance(value, ReconciliationRefused)]
    assert len(applied) == 1
    assert len(refused) == 1
    records = _records(recovered)
    assert len(records) == 1
    assert _execution_rows(recovered)[0]["state"] == applied[0].resulting_state
    assert len(_events(recovered, "action.effect_reconciled")) == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"action_id": "action-step-one"}, "does not match"),
        ({"action_digest": "0" * 64}, "does not match"),
        ({"execution_id": "action-execution-missing"}, "does not exist"),
        ({"task_id": "task-missing"}, "does not exist"),
    ],
)
def test_wrong_action_identity_is_refused(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match=message):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE, **overrides)

    assert _snapshot(recovered) == snapshot


def test_wrong_execution_identity_is_refused(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def step_three_uncertain(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        if action["path"] == "step-three.txt":
            raise RuntimeError("timeout after dispatch")
        from ari_core.modules.execution import execute_action

        return execute_action(action, root)

    recovered = _recovered_task(tmp_path, steps=3, action_executor=step_three_uncertain)
    assert recovered.resume().idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert recovered.resume().idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    succeeded, uncertain = _execution_rows(recovered)
    snapshot = _snapshot(recovered)

    # Another execution's id paired with the uncertain action's identity.
    with pytest.raises(ReconciliationRefused, match="does not match"):
        _reconcile(
            recovered,
            ABSENT,
            ABSENT_EVIDENCE,
            execution=uncertain,
            execution_id=succeeded["execution_id"],
        )
    # A fully consistent identity that names an execution with no uncertainty.
    with pytest.raises(ReconciliationRefused, match="not eligible"):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE, execution=succeeded)

    assert _snapshot(recovered) == snapshot
    assert len(calls) == 2


def test_stale_superseded_attempt_cannot_reconcile(tmp_path: Path) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    replacement = _replace_worker(recovered)
    snapshot = _snapshot(replacement)

    for stale_attempt in (recovered.attempt_id, recovered.old_attempt_id):
        with pytest.raises(ReconciliationRefused, match="active attempt"):
            _reconcile(recovered, ABSENT, ABSENT_EVIDENCE, attempt_id=stale_attempt)

    assert _snapshot(replacement) == snapshot
    result = _reconcile(replacement, ABSENT, ABSENT_EVIDENCE)
    assert result.attempt_id == replacement.attempt_id
    assert _records(replacement)[0]["reserving_attempt_id"] == recovered.attempt_id


def test_stale_active_attempt_cannot_reconcile_until_recovered(tmp_path: Path) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    recovered.clock.advance(seconds=301)  # the active attempt's lease expires
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match="stale"):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)

    assert _snapshot(recovered) == snapshot
    replacement = _replace_worker(recovered)
    assert _reconcile(replacement, ABSENT, ABSENT_EVIDENCE).transitioned is True


def test_expired_lease_under_a_non_worker_gate_is_not_stale(tmp_path: Path) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    recovered.sessions.set_task_lifecycle(
        recovered.task_id, TaskLifecycleState.PAUSED, reason="operator paused"
    )
    recovered.clock.advance(seconds=301)

    result = _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)

    assert result.transitioned is True
    assert recovered.resume().executed is False


def test_terminal_task_is_not_reconciled(tmp_path: Path) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    recovered.sessions.set_task_lifecycle(
        recovered.task_id, TaskLifecycleState.CANCELLED, reason="operator cancelled"
    )
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match="terminal"):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)

    assert _snapshot(recovered) == snapshot


def test_in_flight_execution_cannot_be_reconciled(tmp_path: Path) -> None:
    holder: dict[str, RecoveredFixture] = {}
    refusals: list[ReconciliationRefused] = []

    def executor_that_races_reconciliation(action: dict[str, Any], root: Path | str | None):
        try:
            _reconcile(holder["fixture"], ABSENT, ABSENT_EVIDENCE)
        except ReconciliationRefused as error:
            refusals.append(error)
        from ari_core.modules.execution import execute_action

        return execute_action(action, root)

    recovered = _recovered_task(tmp_path, action_executor=executor_that_races_reconciliation)
    holder["fixture"] = recovered

    result = recovered.resume()

    assert len(refusals) == 1
    assert "in flight" in str(refusals[0])
    assert result.idempotency_state is ActionIdempotencyState.SUCCEEDED
    assert _records(recovered) == []


def test_crash_after_dispatch_is_reconcilable_by_replacement_attempt(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def crashing_executor(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        (Path(root) / str(action["path"])).write_text(str(action["content"]), encoding="utf-8")
        raise SimulatedCrash()

    recovered = _recovered_task(tmp_path, action_executor=crashing_executor)
    with pytest.raises(SimulatedCrash):
        recovered.resume()
    assert _execution_rows(recovered)[0]["state"] == "executing"
    replacement = _replace_worker(recovered)

    # No resume call is needed to persist the derived uncertainty first.
    result = _reconcile(replacement, CONFIRMED, PRESENT_EVIDENCE)
    record = _records(replacement)[0]

    assert result.previous_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert record["previous_state"] == "executing"
    assert record["effective_previous_state"] == "effect_may_have_occurred"
    assert _execution_rows(replacement)[0]["state"] == "effect_confirmed"
    after = replacement.resume()
    assert after.executed is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("evidence", "outcome", "message"),
    [
        ([], ABSENT, "At least one"),
        ("the file looked fine", ABSENT, "sequence"),
        ({"kind": "x", "summary": "y", "indicates": "effect_absent"}, ABSENT, "sequence"),
        ([42], ABSENT, "mapping"),
        ([{**ABSENT_EVIDENCE[0], "kind": " "}], ABSENT, "kind is required"),
        ([{**ABSENT_EVIDENCE[0], "summary": None}], ABSENT, "summary is required"),
        ([{**ABSENT_EVIDENCE[0], "indicates": "probably_absent"}], ABSENT, "indicates"),
        ([{**ABSENT_EVIDENCE[0], "details": "not-a-mapping"}], ABSENT, "details"),
        ([{**ABSENT_EVIDENCE[0], "reference": ""}], ABSENT, "reference"),
        ([{**ABSENT_EVIDENCE[0], "verdict": "absent"}], ABSENT, "unknown fields"),
        (ABSENT_EVIDENCE, "retry_now", "Unknown reconciliation outcome"),
    ],
)
def test_malformed_evidence_is_refused(
    tmp_path: Path,
    evidence: Any,
    outcome: Any,
    message: str,
) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match=message):
        _reconcile(recovered, outcome, evidence)

    assert _snapshot(recovered) == snapshot


@pytest.mark.parametrize(
    ("field", "value"),
    [("reconciled_by", " "), ("reason", "")],
)
def test_missing_reconciler_identity_or_reason_is_refused(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    snapshot = _snapshot(recovered)

    with pytest.raises(ReconciliationRefused, match="required"):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE, **{field: value})

    assert _snapshot(recovered) == snapshot


def test_persistence_failure_rolls_back_the_whole_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recovered, _calls = _uncertain(tmp_path, write=False)
    snapshot = _snapshot(recovered)
    original_insert = ExecutionLedger._insert_boundary

    def failing_insert(connection, **kwargs):
        if kwargs["trigger"] == "effect_reconciled":
            raise sqlite3.OperationalError("disk I/O error")
        return original_insert(connection, **kwargs)

    monkeypatch.setattr(ExecutionLedger, "_insert_boundary", staticmethod(failing_insert))
    with pytest.raises(sqlite3.OperationalError):
        _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    monkeypatch.undo()

    assert _snapshot(recovered) == snapshot
    # The failed request left nothing behind, so the same request is not a duplicate.
    retried = _reconcile(recovered, ABSENT, ABSENT_EVIDENCE)
    assert retried.duplicate is False
    assert retried.transitioned is True


@pytest.mark.parametrize(
    "stage",
    ["validated", "record_inserted", "execution_updated", "checkpoint_inserted"],
)
def test_crash_inside_reconciliation_transaction_leaves_no_partial_state(
    tmp_path: Path,
    stage: str,
) -> None:
    recovered, _calls = _uncertain(tmp_path, write=True)
    snapshot = _snapshot(recovered)

    def crash_at(current: str) -> None:
        if current == stage:
            raise SimulatedCrash()

    crashing = EffectReconciler(recovered.db_path, clock=recovered.clock, transaction_hook=crash_at)
    with pytest.raises(SimulatedCrash):
        _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE, reconciler=crashing)

    assert _snapshot(recovered) == snapshot
    assert _reconcile(recovered, CONFIRMED, PRESENT_EVIDENCE).transitioned is True


def test_reconciliation_record_survives_restart(tmp_path: Path) -> None:
    recovered, calls = _uncertain(tmp_path, write=False)
    row = _execution_rows(recovered)[0]
    result = _reconcile(
        recovered,
        ABSENT,
        ABSENT_EVIDENCE,
        provenance={"authority": "alec", "channel": "operator-console"},
    )

    restarted_reconciler = EffectReconciler(recovered.db_path)
    restarted_gateway = RecoveredActionGateway(
        recovered.db_path,
        execution_root=recovered.root,
        clock=recovered.clock,
        pause_state_reader=lambda: {"paused": False, "reason": None},
        action_executor=_counting_executor(calls),
    )
    [record] = restarted_reconciler.list_reconciliations(recovered.task_id)

    assert record["reconciliation_id"] == result.reconciliation_id
    assert record["execution_id"] == row["execution_id"]
    assert record["decision_id"] == row["decision_id"]
    assert record["idempotency_key"] == row["idempotency_key"]
    assert record["reserving_attempt_id"] == row["attempt_id"]
    assert record["attempt_id"] == recovered.attempt_id
    assert record["previous_state"] == "effect_may_have_occurred"
    assert record["resulting_state"] == "effect_confirmed_absent"
    assert record["retry_eligible"] == 1
    assert record["reconciled_by"] == "alec"
    assert record["reason"] == "Inspected the target resource directly."
    assert record["evidence"] == [
        {**ABSENT_EVIDENCE[0], "observed_at": None, "details": {}}
    ]
    assert len(record["evidence_sha256"]) == 64
    assert record["basis_checkpoint_id"] is not None
    assert record["checkpoint_id"] == result.checkpoint_id
    assert record["provenance"] == {"authority": "alec", "channel": "operator-console"}
    assert record["created_at"] == "2026-10-01T12:00:06Z"

    reloaded = restarted_gateway.resume_one(
        task_id=recovered.task_id,
        attempt_id=recovered.attempt_id,
        worker_identity=recovered.worker_identity,
        session_id=recovered.session_id,
    )
    assert reloaded.executed is False
    assert reloaded.idempotency_state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("outcome", "evidence", "expected_state", "pending_after"),
    [
        (CONFIRMED, PRESENT_EVIDENCE, "effect_confirmed", []),
        (ABSENT, ABSENT_EVIDENCE, "effect_confirmed_absent", ["action-step-two"]),
    ],
)
def test_verification_failed_uses_the_same_reconciliation(
    tmp_path: Path,
    outcome: EffectReconciliationOutcome,
    evidence: list[dict[str, Any]],
    expected_state: str,
    pending_after: list[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def lying_executor(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        return {"success": True, "path": str(action["path"])}

    recovered = _recovered_task(tmp_path, action_executor=lying_executor)
    first = recovered.resume()
    assert first.idempotency_state is ActionIdempotencyState.VERIFICATION_FAILED

    result = _reconcile(recovered, outcome, evidence)
    latest = recovered.gateway._latest_checkpoint(recovered.task_id)

    assert result.previous_state is ActionIdempotencyState.VERIFICATION_FAILED
    assert _execution_rows(recovered)[0]["state"] == expected_state
    assert [step["action_id"] for step in latest["pending_steps"]] == pending_after
    assert recovered.resume().executed is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("outcome", "evidence", "expected_state", "reopened"),
    [
        (ABSENT, ABSENT_EVIDENCE, "effect_may_have_occurred", True),
        (CONFIRMED, PRESENT_EVIDENCE, "effect_confirmed", False),
    ],
)
def test_late_report_from_superseded_attempt_cannot_overwrite_reconciled_truth(
    tmp_path: Path,
    outcome: EffectReconciliationOutcome,
    evidence: list[dict[str, Any]],
    expected_state: str,
    reopened: bool,
) -> None:
    """A zombie worker finishing after reconciliation is evidence, never a silent overwrite.

    A late result after "confirmed absent" contradicts it, so the action returns to
    uncertain and even an explicit plan revision cannot re-run it.
    """
    holder: dict[str, RecoveredFixture] = {}
    replacements: list[RecoveredFixture] = []
    reconciliations: list[Any] = []
    calls: list[dict[str, Any]] = []

    def zombie_executor(action: dict[str, Any], root: Path | str | None):
        calls.append(action)
        replacement = _replace_worker(holder["fixture"])
        replacements.append(replacement)
        reconciliations.append(_reconcile(replacement, outcome, evidence))
        (Path(root) / str(action["path"])).write_text(str(action["content"]), encoding="utf-8")
        return {"success": True, "path": str(action["path"])}

    recovered = _recovered_task(tmp_path, action_executor=zombie_executor)
    holder["fixture"] = recovered

    zombie = recovered.resume()
    replacement = replacements[0]
    row = _execution_rows(replacement)[0]
    [record] = _records(replacement)
    [late_event] = _events(replacement, "action.late_report_after_reconciliation")

    assert zombie.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN
    assert reconciliations[0].transitioned is True
    assert row["state"] == expected_state
    assert row["reconciliation_id"] == record["reconciliation_id"]
    assert record["resulting_state"] == reconciliations[0].resulting_state
    assert late_event["payload"]["reopened_as_uncertain"] is reopened
    assert late_event["payload"]["result"]["success"] is True

    _revise_step_two(replacement, "retry after reconciliation\n")
    retry = replacement.resume()
    assert retry.executed is False
    assert len(calls) == 1
