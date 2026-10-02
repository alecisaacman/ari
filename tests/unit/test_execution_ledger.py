from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from ari_core.modules.execution import (
    CheckpointState,
    ExecutionController,
    ExecutionGoal,
    ExecutionLedger,
    ExecutionTaskSpec,
    ModelPlanner,
    PlannerResult,
    WorkerAction,
    WorkerPlan,
)
from ari_core.modules.networking.db import get_connection


def _create_ledger_task(ledger: ExecutionLedger) -> tuple[str, str]:
    task_id = "task-ledger-test"
    return ledger.create_task(
        ExecutionTaskSpec(
            task_id=task_id,
            objective="Prove durable task state.",
            success_criteria=("The checkpoint can be recovered.",),
            authority_snapshot_ref="approval-snapshot-1",
            authority_snapshot_hash="sha256:authority",
        ),
        executor_id="test-executor",
        backend_id="test-backend",
        provenance={"source": "unit-test"},
    )


def test_task_creation_produces_initial_durable_checkpoint(tmp_path: Path) -> None:
    ledger = ExecutionLedger(tmp_path / "state" / "ari.db")
    task_id, attempt_id = _create_ledger_task(ledger)

    bundle = ledger.get_task_bundle(task_id)

    assert bundle is not None
    assert bundle["task"]["latest_checkpoint_id"] == bundle["checkpoints"][0][
        "checkpoint_id"
    ]
    assert bundle["checkpoints"][0]["trigger"] == "task_accepted"
    assert bundle["checkpoints"][0]["attempt_id"] == attempt_id
    assert bundle["events"][0]["event_type"] == "task.accepted"


@pytest.mark.parametrize(
    "failure_stage",
    [
        "task_inserted",
        "attempt_inserted",
        "event_inserted",
        "checkpoint_inserted",
        "task_linked",
        "initialization_complete",
    ],
)
def test_task_initialization_rolls_back_at_every_boundary(
    tmp_path: Path,
    failure_stage: str,
) -> None:
    db_path = tmp_path / failure_stage / "ari.db"

    def fail_at_boundary(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected initialization failure at {stage}")

    ledger = ExecutionLedger(db_path, initialization_hook=fail_at_boundary)
    with pytest.raises(RuntimeError, match="injected initialization failure"):
        _create_ledger_task(ledger)

    with get_connection(db_path) as connection:
        counts = {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "ari_execution_tasks",
                "ari_execution_attempts",
                "ari_execution_events",
                "ari_execution_checkpoints",
            )
        }
    assert counts == {
        "ari_execution_tasks": 0,
        "ari_execution_attempts": 0,
        "ari_execution_events": 0,
        "ari_execution_checkpoints": 0,
    }


def test_schema_migration_is_versioned_and_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "ari.db"

    ExecutionLedger(db_path)
    ExecutionLedger(db_path)

    with get_connection(db_path) as connection:
        migrations = connection.execute(
            "select version, checksum from ari_schema_migrations order by version"
        ).fetchall()
        tables = {
            row["name"]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
    assert [row["version"] for row in migrations] == [
        "0001_execution_fabric",
        "0002_execution_sessions",
        "0003_recovered_action_gateway",
        "0004_effect_reconciliation",
        "0005_dispatch_fences",
        "0006_redispatch_safety",
    ]
    assert all(len(row["checksum"]) == 64 for row in migrations)
    assert {
        "ari_execution_tasks",
        "ari_execution_attempts",
        "ari_execution_checkpoints",
        "ari_execution_events",
        "ari_execution_results",
        "ari_execution_action_approvals",
        "ari_execution_resume_decisions",
        "ari_execution_action_executions",
        "ari_execution_effect_reconciliations",
        "ari_execution_dispatch_fences",
    }.issubset(tables)


def test_events_and_checkpoints_are_ordered_and_results_use_common_contract(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "ari.db"
    root = tmp_path / "repo"
    root.mkdir()
    goal = ExecutionGoal(
        objective="write files alpha.txt with alpha; beta.txt with beta",
        success_criteria=("Both files are verified.",),
        authority_snapshot_ref="approval-snapshot-2",
    )

    run = ExecutionController(execution_root=root, db_path=db_path).run(goal)
    bundle = ExecutionLedger(db_path).get_task_bundle(goal.task_id)

    assert run.status == "completed"
    assert run.task_id == goal.task_id
    assert run.canonical_result is not None
    assert bundle is not None
    assert [event["sequence"] for event in bundle["events"]] == list(
        range(1, len(bundle["events"]) + 1)
    )
    assert bundle["events"][-1]["event_type"] == "result.recorded"
    assert [item["sequence"] for item in bundle["checkpoints"]] == list(
        range(1, len(bundle["checkpoints"]) + 1)
    )
    assert bundle["result"]["status"] == "completed"
    assert bundle["result"]["task_id"] == goal.task_id
    assert bundle["result"]["success_criteria_evaluation"][0]["satisfied"] is True
    assert {artifact["path"] for artifact in bundle["result"]["artifacts"]} == {
        "alpha.txt",
        "beta.txt",
    }
    assert bundle["task"]["authority_snapshot_ref"] == "approval-snapshot-2"
    assert bundle["task"]["plan_revision"] == 1
    assert any(item["trigger"] == "plan_created" for item in bundle["checkpoints"])
    assert any(item["trigger"] == "verification_completed" for item in bundle["checkpoints"])
    assert bundle["result"]["verification"]


def test_two_step_execution_recovers_latest_checkpoint_after_simulated_crash(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "ari.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "first.txt").write_text("old first\n", encoding="utf-8")
    (root / "second.txt").write_text("old second\n", encoding="utf-8")
    task_id = "task-crash-recovery"
    planner = ModelPlanner(
        lambda _payload: json.dumps(
            {
                "confidence": 0.99,
                "reason": "Perform two independently checkpointed writes.",
                "actions": [
                    {"type": "write_file", "path": "first.txt", "content": "one\n"},
                    {"type": "write_file", "path": "second.txt", "content": "two\n"},
                ],
            }
        )
    )

    class SimulatedProcessCrash(BaseException):
        pass

    def crash_after_first_action(trigger: str, payload: dict[str, object]) -> None:
        checkpoint = payload["checkpoint"]
        assert isinstance(checkpoint, dict)
        if trigger == "action_completed" and len(checkpoint["completed_steps"]) == 1:
            raise SimulatedProcessCrash

    controller = ExecutionController(
        execution_root=root,
        db_path=db_path,
        planner=planner,
        lifecycle_hook=crash_after_first_action,
    )
    goal = ExecutionGoal(
        task_id=task_id,
        objective="Create two durable files.",
        success_criteria=("Both writes complete and verify.",),
        authority_snapshot_ref="approval-snapshot-crash",
        authority_snapshot_hash="sha256:crash-authority",
    )

    with pytest.raises(SimulatedProcessCrash):
        controller.run(goal)

    assert (root / "first.txt").read_text(encoding="utf-8") == "one\n"
    assert (root / "second.txt").read_text(encoding="utf-8") == "old second\n"

    recovered_ledger = ExecutionLedger(db_path)
    continuation = recovered_ledger.prepare_continuation(task_id)
    bundle = recovered_ledger.get_task_bundle(task_id)

    assert continuation is not None
    assert continuation["task_id"] == task_id
    assert continuation["objective"] == "Create two durable files."
    assert continuation["success_criteria"] == ["Both writes complete and verify."]
    assert continuation["completed_steps"][0]["action_type"] == "write_file"
    assert continuation["pending_steps"][0]["action_type"] == "write_file"
    assert continuation["next_recommended_action"]
    assert continuation["authority_snapshot_ref"] == "approval-snapshot-crash"
    assert continuation["acknowledgement_required"] is True
    assert bundle is not None
    assert bundle["result"] is None
    latest = bundle["checkpoints"][-1]
    assert latest["trigger"] == "action_completed"
    assert latest["artifacts"][0]["path"] == "first.txt"
    assert len(latest["artifacts"][0]["sha256"]) == 64
    assert latest["provenance"]["goal_id"] == goal.id

    replacement_attempt = recovered_ledger.start_attempt(
        task_id,
        executor_id="replacement-worker",
        backend_id="replacement-backend",
        continuation_checkpoint_id=continuation["checkpoint_id"],
        provenance={"reason": "simulated crash recovery"},
    )
    recovered = recovered_ledger.get_task_bundle(task_id)
    assert recovered is not None
    assert recovered["attempts"][-1]["attempt_id"] == replacement_attempt
    assert recovered["attempts"][-1]["continuation_checkpoint_id"] == (
        continuation["checkpoint_id"]
    )


def test_boundary_event_and_checkpoint_roll_back_together(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "ari.db"
    ledger = ExecutionLedger(db_path)
    task_id, attempt_id = _create_ledger_task(ledger)
    before = ledger.get_task_bundle(task_id)
    assert before is not None
    with get_connection(db_path) as connection:
        connection.executescript(
            """
            create trigger abort_forced_checkpoint
            before insert on ari_execution_checkpoints
            when new.trigger = 'force_rollback'
            begin
                select raise(abort, 'forced checkpoint failure');
            end;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced checkpoint failure"):
        ledger.record_boundary(
            task_id=task_id,
            attempt_id=attempt_id,
            trigger="force_rollback",
            event_type="test.force_rollback",
            state=CheckpointState(
                objective="Prove durable task state.",
                success_criteria=("The checkpoint can be recovered.",),
            ),
        )

    after = ledger.get_task_bundle(task_id)
    assert after is not None
    assert len(after["events"]) == len(before["events"])
    assert len(after["checkpoints"]) == len(before["checkpoints"])
    assert after["task"]["latest_checkpoint_id"] == before["task"]["latest_checkpoint_id"]


def test_approval_required_action_remains_blocked_and_is_recorded(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "ari.db"
    root = tmp_path / "repo"
    root.mkdir()

    class ApprovalRequiredPlanner:
        planner_name = "approval-required-test"

        def plan(self, *args: object, **kwargs: object) -> PlannerResult:
            del args, kwargs
            return PlannerResult(
                status="act",
                reason="Propose a gated mutation.",
                confidence=1.0,
                planner_name=self.planner_name,
                plan=WorkerPlan(
                    actions=(
                        WorkerAction(
                            action_type="write_file",
                            payload={"path": "blocked.txt", "content": "must not write"},
                            reason="Requires Alec's approval.",
                            requires_approval=True,
                        ),
                    ),
                    verification=(),
                    reason="Approval gate proof.",
                ),
            )

    goal = ExecutionGoal(
        objective="Attempt an approval-gated write.",
        authority_snapshot_ref="pending-approval-1",
    )
    run = ExecutionController(
        execution_root=root,
        db_path=db_path,
        planner=ApprovalRequiredPlanner(),
    ).run(goal)
    bundle = ExecutionLedger(db_path).get_task_bundle(goal.task_id)

    assert run.status == "rejected"
    assert "requires approval" in run.reason
    assert not (root / "blocked.txt").exists()
    assert bundle is not None
    assert bundle["task"]["authority_snapshot_ref"] == "pending-approval-1"
    assert bundle["result"]["status"] == "rejected"


def test_persisted_payloads_redact_secrets_and_bound_large_output(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "ari.db"
    ledger = ExecutionLedger(db_path)
    task_id, attempt_id = _create_ledger_task(ledger)

    checkpoint = ledger.record_boundary(
        task_id=task_id,
        attempt_id=attempt_id,
        trigger="tool_result",
        event_type="tool.result",
        state=CheckpointState(
            objective="Prove durable task state.",
            success_criteria=("The checkpoint can be recovered.",),
            actions_taken=(
                {
                    "api_key": "sk-this-must-not-survive",
                    "stdout": "x" * 3000,
                    "note": "Bearer abcdefghijklmnopqrstuvwxyz",
                },
            ),
        ),
    )

    persisted = json.dumps(checkpoint)
    assert "sk-this-must-not-survive" not in persisted
    assert "abcdefghijklmnopqrstuvwxyz" not in persisted
    assert "[REDACTED]" in persisted
    assert "[truncated 1000 chars]" in persisted
