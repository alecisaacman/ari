from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database
from .contracts import (
    AttemptLifecycleState,
    CheckpointState,
    ExecutionResultContract,
    ExecutionTaskSpec,
    TaskLifecycleState,
)
from .models import _now_iso

_SENSITIVE_KEY = re.compile(r"(api.?key|authorization|cookie|password|secret|token)", re.I)
_SENSITIVE_VALUE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._-]{12,}|(?<![a-z0-9])sk-[a-z0-9_-]{12,}|"
    r"xox[baprs]-[a-z0-9-]{10,})"
)
_JSON_COLUMNS = {
    "success_criteria_json",
    "requirements_json",
    "current_plan_json",
    "failure_json",
    "provenance_json",
    "completed_steps_json",
    "pending_steps_json",
    "important_findings_json",
    "assumptions_json",
    "decisions_json",
    "artifacts_json",
    "actions_taken_json",
    "verification_results_json",
    "errors_json",
    "provider_json",
    "capacity_observations_json",
    "payload_json",
    "success_criteria_evaluation_json",
    "evidence_json",
    "verification_json",
    "unresolved_issues_json",
    "decisions_requiring_alec_json",
    "provider_provenance_json",
    "execution_history_json",
    "restrictions_json",
    "authority_scope_json",
    "approval_state_json",
    "recovery_json",
    "metadata_json",
    "packet_json",
    "acknowledgement_json",
}


class ExecutionLedger:
    """Durable, provider-neutral state for bounded execution work."""

    def __init__(
        self,
        db_path: Path = DB_PATH,
        *,
        initialization_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.db_path = db_path
        self.initialization_hook = initialization_hook
        initialize_database(db_path)

    def create_task(
        self,
        spec: ExecutionTaskSpec,
        *,
        executor_id: str,
        backend_id: str,
        model_ref: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        attempt_id = f"attempt-{uuid4()}"
        now = _now_iso()
        clean_provenance = sanitize_payload(provenance or {})
        initial = CheckpointState(
            objective=spec.objective,
            success_criteria=spec.success_criteria,
            next_recommended_action="Create and validate the first bounded execution plan.",
            provider={
                "executor_id": executor_id,
                "backend_id": backend_id,
                "model_ref": model_ref,
            },
            provenance=clean_provenance,
            restrictions=spec.restrictions,
            authority_scope=spec.authority_scope,
            approval_state=spec.approval_state,
        )
        with self._transaction() as connection:
            connection.execute(
                """
                insert into ari_execution_tasks (
                    task_id, objective, success_criteria_json, requirements_json,
                    status, current_plan_json, linked_project_id, linked_task_id,
                    linked_milestone_id, linked_goal_id, authority_snapshot_ref,
                    authority_snapshot_hash, restrictions_json, authority_scope_json,
                    approval_state_json, lifecycle_state, active_attempt_id,
                    created_at, updated_at
                ) values (?, ?, ?, ?, 'running', '{}', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'waiting_for_worker', ?, ?, ?)
                """,
                (
                    spec.task_id,
                    spec.objective,
                    _json(spec.success_criteria),
                    _json(spec.requirements),
                    spec.linked_project_id,
                    spec.linked_task_id,
                    spec.linked_milestone_id,
                    spec.linked_goal_id,
                    spec.authority_snapshot_ref,
                    spec.authority_snapshot_hash,
                    _json(spec.restrictions),
                    _json(spec.authority_scope),
                    _json(spec.approval_state),
                    attempt_id,
                    now,
                    now,
                ),
            )
            self._initialization_boundary("task_inserted")
            self._insert_attempt(
                connection,
                attempt_id=attempt_id,
                task_id=spec.task_id,
                executor_id=executor_id,
                backend_id=backend_id,
                model_ref=model_ref,
                continuation_checkpoint_id=None,
                provenance=clean_provenance,
                now=now,
            )
            self._initialization_boundary("attempt_inserted")
            self._insert_boundary(
                connection,
                checkpoint_id=f"checkpoint-{uuid4()}",
                event_id=f"event-{uuid4()}",
                task_id=spec.task_id,
                attempt_id=attempt_id,
                trigger="task_accepted",
                event_type="task.accepted",
                state_payload=sanitize_payload(asdict(initial)),
                event_payload=sanitize_payload({"task_spec": spec.to_dict()}),
                idempotency_key=f"task-initialized:{spec.task_id}",
                now=now,
                initialization=True,
                initialization_hook=self.initialization_hook,
            )
            self._initialization_boundary("initialization_complete")
        return spec.task_id, attempt_id

    def start_attempt(
        self,
        task_id: str,
        *,
        executor_id: str,
        backend_id: str,
        model_ref: str | None = None,
        continuation_checkpoint_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        attempt_id = f"attempt-{uuid4()}"
        with self._transaction() as connection:
            self._require_task(connection, task_id)
            self._insert_attempt(
                connection,
                attempt_id=attempt_id,
                task_id=task_id,
                executor_id=executor_id,
                backend_id=backend_id,
                model_ref=model_ref,
                continuation_checkpoint_id=continuation_checkpoint_id,
                provenance=sanitize_payload(provenance or {}),
                now=_now_iso(),
            )
        return attempt_id

    def record_boundary(
        self,
        *,
        task_id: str,
        attempt_id: str,
        trigger: str,
        event_type: str,
        state: CheckpointState,
        event_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        checkpoint_id = f"checkpoint-{uuid4()}"
        event_id = f"event-{uuid4()}"
        now = _now_iso()
        state_payload = sanitize_payload(asdict(state))
        clean_event = sanitize_payload(event_payload or {})
        with self._transaction() as connection:
            self._insert_boundary(
                connection,
                checkpoint_id=checkpoint_id,
                event_id=event_id,
                task_id=task_id,
                attempt_id=attempt_id,
                trigger=trigger,
                event_type=event_type,
                state_payload=state_payload,
                event_payload=clean_event,
                idempotency_key=idempotency_key,
                now=now,
            )
        checkpoint = self.get_checkpoint(checkpoint_id)
        assert checkpoint is not None
        return checkpoint

    def record_result(
        self,
        *,
        task_id: str,
        attempt_id: str,
        result: ExecutionResultContract,
        final_checkpoint_id: str,
    ) -> dict[str, Any]:
        result_id = f"result-{uuid4()}"
        now = _now_iso()
        payload = sanitize_payload(result.to_dict())
        if payload["task_id"] != task_id:
            raise ValueError("Result task_id must match the canonical execution task.")
        attempt_lifecycle = (
            AttemptLifecycleState.SUCCEEDED
            if payload["status"] == "completed"
            else AttemptLifecycleState.CANCELLED
            if payload["status"] == "cancelled"
            else AttemptLifecycleState.FAILED
        )
        task_lifecycle = (
            TaskLifecycleState.SUCCEEDED
            if payload["status"] == "completed"
            else TaskLifecycleState.CANCELLED
            if payload["status"] == "cancelled"
            else TaskLifecycleState.FAILED
        )
        with self._transaction() as connection:
            self._require_task(connection, task_id)
            event_sequence = self._next_sequence(connection, "ari_execution_events", task_id)
            connection.execute(
                """
                insert into ari_execution_events (
                    event_id, task_id, attempt_id, sequence, event_type,
                    payload_json, provenance_json, created_at
                ) values (?, ?, ?, ?, 'result.recorded', ?, ?, ?)
                """,
                (
                    f"event-{uuid4()}",
                    task_id,
                    attempt_id,
                    event_sequence,
                    _json(
                        {
                            "result_id": result_id,
                            "status": payload["status"],
                            "outcome": payload["outcome"],
                        }
                    ),
                    _json(payload["provider_provenance"]),
                    now,
                ),
            )
            connection.execute(
                """
                insert into ari_execution_results (
                    result_id, task_id, status, objective, outcome,
                    success_criteria_evaluation_json, artifacts_json, evidence_json,
                    verification_json, unresolved_issues_json,
                    decisions_requiring_alec_json, recommended_next_action,
                    provider_provenance_json, execution_history_json,
                    final_checkpoint_id, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    task_id,
                    payload["status"],
                    payload["objective"],
                    payload["outcome"],
                    _json(payload["success_criteria_evaluation"]),
                    _json(payload["artifacts"]),
                    _json(payload["evidence"]),
                    _json(payload["verification"]),
                    _json(payload["unresolved_issues"]),
                    _json(payload["decisions_requiring_alec"]),
                    payload["recommended_next_action"],
                    _json(payload["provider_provenance"]),
                    _json(payload["execution_history"]),
                    final_checkpoint_id,
                    now,
                ),
            )
            connection.execute(
                """
                update ari_execution_attempts
                set status = ?, lifecycle_state = ?, ended_at = ?
                where attempt_id = ?
                """,
                (payload["status"], attempt_lifecycle, now, attempt_id),
            )
            connection.execute(
                """
                update ari_execution_tasks
                set status = ?, lifecycle_state = ?, result_id = ?, updated_at = ?,
                    row_version = row_version + 1
                where task_id = ?
                """,
                (payload["status"], task_lifecycle, result_id, now, task_id),
            )
        stored = self.get_result(task_id)
        assert stored is not None
        return stored

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._one("select * from ari_execution_tasks where task_id = ?", (task_id,))

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        return self._one(
            "select * from ari_execution_checkpoints where checkpoint_id = ?",
            (checkpoint_id,),
        )

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        return self._one("select * from ari_execution_results where task_id = ?", (task_id,))

    def get_task_bundle(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        return {
            "task": task,
            "attempts": self._many(
                "select * from ari_execution_attempts where task_id = ? order by started_at, rowid",
                (task_id,),
            ),
            "checkpoints": self._many(
                "select * from ari_execution_checkpoints where task_id = ? order by sequence",
                (task_id,),
            ),
            "events": self._many(
                "select * from ari_execution_events where task_id = ? order by sequence",
                (task_id,),
            ),
            "result": self.get_result(task_id),
        }

    def prepare_continuation(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if task is None or task["latest_checkpoint_id"] is None:
            return None
        checkpoint = self.get_checkpoint(task["latest_checkpoint_id"])
        assert checkpoint is not None
        return {
            "task_id": task_id,
            "objective": checkpoint["objective"],
            "success_criteria": checkpoint["success_criteria"],
            "completed_steps": checkpoint["completed_steps"],
            "pending_steps": checkpoint["pending_steps"],
            "next_recommended_action": checkpoint["next_recommended_action"],
            "checkpoint_id": checkpoint["checkpoint_id"],
            "authority_snapshot_ref": checkpoint["authority_snapshot_ref"],
            "authority_snapshot_hash": checkpoint["authority_snapshot_hash"],
            "provenance": checkpoint["provenance"],
            "acknowledgement_required": True,
        }

    def _one(self, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(sql, parameters).fetchone()
        return None if row is None else _decode_row(row)

    def _many(self, sql: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [_decode_row(row) for row in rows]

    def _transaction(self) -> _ImmediateTransaction:
        return _ImmediateTransaction(self.db_path)

    @staticmethod
    def _require_task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "select * from ari_execution_tasks where task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Execution task {task_id} does not exist.")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _next_sequence(connection: sqlite3.Connection, table: str, task_id: str) -> int:
        if table not in {"ari_execution_checkpoints", "ari_execution_events"}:
            raise ValueError("Unsupported sequence table.")
        row = connection.execute(
            f"select coalesce(max(sequence), 0) + 1 as next_sequence from {table} where task_id = ?",
            (task_id,),
        ).fetchone()
        return int(row["next_sequence"])

    @staticmethod
    def _insert_boundary(
        connection: sqlite3.Connection,
        *,
        checkpoint_id: str,
        event_id: str,
        task_id: str,
        attempt_id: str,
        trigger: str,
        event_type: str,
        state_payload: dict[str, Any],
        event_payload: dict[str, Any],
        idempotency_key: str | None,
        now: str,
        initialization: bool = False,
        initialization_hook: Callable[[str], None] | None = None,
    ) -> None:
        task = ExecutionLedger._require_task(connection, task_id)
        attempt = connection.execute(
            "select * from ari_execution_attempts where attempt_id = ? and task_id = ?",
            (attempt_id, task_id),
        ).fetchone()
        if attempt is None:
            raise ValueError(f"Attempt {attempt_id} does not belong to task {task_id}.")
        checkpoint_sequence = ExecutionLedger._next_sequence(
            connection, "ari_execution_checkpoints", task_id
        )
        event_sequence = ExecutionLedger._next_sequence(
            connection, "ari_execution_events", task_id
        )
        parent_id = task["latest_checkpoint_id"]
        payload_hash = hashlib.sha256(_json(state_payload).encode("utf-8")).hexdigest()
        connection.execute(
            """
            insert into ari_execution_events (
                event_id, task_id, attempt_id, sequence, event_type,
                idempotency_key, payload_json, provenance_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                task_id,
                attempt_id,
                event_sequence,
                event_type,
                idempotency_key,
                _json(event_payload),
                _json(state_payload["provenance"]),
                now,
            ),
        )
        if initialization and initialization_hook is not None:
            initialization_hook("event_inserted")
        connection.execute(
            """
            insert into ari_execution_checkpoints (
                checkpoint_id, task_id, attempt_id, sequence, trigger, objective,
                success_criteria_json, current_plan_json, completed_steps_json,
                pending_steps_json, important_findings_json, assumptions_json,
                decisions_json, artifacts_json, actions_taken_json,
                verification_results_json, errors_json, provider_json,
                capacity_observations_json, next_recommended_action,
                authority_snapshot_ref, authority_snapshot_hash, restrictions_json,
                authority_scope_json, approval_state_json, parent_checkpoint_id,
                payload_sha256, provenance_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                task_id,
                attempt_id,
                checkpoint_sequence,
                trigger,
                state_payload["objective"],
                _json(state_payload["success_criteria"]),
                _json(state_payload["current_plan"]),
                _json(state_payload["completed_steps"]),
                _json(state_payload["pending_steps"]),
                _json(state_payload["important_findings"]),
                _json(state_payload["assumptions"]),
                _json(state_payload["decisions"]),
                _json(state_payload["artifacts"]),
                _json(state_payload["actions_taken"]),
                _json(state_payload["verification_results"]),
                _json(state_payload["errors"]),
                _json(state_payload["provider"]),
                _json(state_payload["capacity_observations"]),
                state_payload["next_recommended_action"],
                task["authority_snapshot_ref"],
                task["authority_snapshot_hash"],
                _json(state_payload["restrictions"]),
                _json(state_payload["authority_scope"]),
                _json(state_payload["approval_state"]),
                parent_id,
                payload_hash,
                _json(state_payload["provenance"]),
                now,
            ),
        )
        if initialization and initialization_hook is not None:
            initialization_hook("checkpoint_inserted")
        connection.execute(
            """
            update ari_execution_tasks
            set current_plan_json = ?, plan_revision = plan_revision + ?,
                latest_checkpoint_id = ?, updated_at = ?,
                row_version = row_version + 1
            where task_id = ?
            """,
            (
                _json(state_payload["current_plan"]),
                int(trigger in {"plan_created", "plan_revised"}),
                checkpoint_id,
                now,
                task_id,
            ),
        )
        if initialization and initialization_hook is not None:
            initialization_hook("task_linked")

    def _initialization_boundary(self, stage: str) -> None:
        if self.initialization_hook is not None:
            self.initialization_hook(stage)

    @staticmethod
    def _insert_attempt(
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        task_id: str,
        executor_id: str,
        backend_id: str,
        model_ref: str | None,
        continuation_checkpoint_id: str | None,
        provenance: dict[str, Any],
        now: str,
    ) -> None:
        connection.execute(
            """
            insert into ari_execution_attempts (
                attempt_id, task_id, executor_id, backend_id, model_ref, status,
                continuation_checkpoint_id, provenance_json, started_at, lifecycle_state
            ) values (?, ?, ?, ?, ?, 'running', ?, ?, ?, 'waiting_for_worker')
            """,
            (
                attempt_id,
                task_id,
                executor_id,
                backend_id,
                model_ref,
                continuation_checkpoint_id,
                _json(provenance),
                now,
            ),
        )


class _ImmediateTransaction:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self.connection = get_connection(self.db_path)
        self.connection.execute("begin immediate")
        return self.connection

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        assert self.connection is not None
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def sanitize_payload(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): sanitize_payload(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item, key=key) for item in value]
    if isinstance(value, str):
        limit = 2000 if key.lower() in {"stdout", "stderr", "content"} else 4000
        redacted = _SENSITIVE_VALUE.sub("[REDACTED]", value)
        if len(redacted) > limit:
            return f"{redacted[:limit]}...[truncated {len(redacted) - limit} chars]"
        return redacted
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    decoded = {key: row[key] for key in row.keys()}
    for column in _JSON_COLUMNS.intersection(decoded):
        raw = decoded[column]
        decoded[column.removesuffix("_json")] = None if raw is None else json.loads(raw)
        del decoded[column]
    return decoded
