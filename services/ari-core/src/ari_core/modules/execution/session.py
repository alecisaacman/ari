from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.paths import DB_PATH
from .contracts import (
    AttemptLifecycleState,
    AttemptRecoveryDecision,
    ContinuationAcknowledgement,
    ContinuationPacket,
    RecoveryClassification,
    TaskLifecycleState,
    WorkerHeartbeat,
    WorkerLease,
    WorkerSession,
)
from .ledger import ExecutionLedger, _json, sanitize_payload

Clock = Callable[[], datetime]

_TERMINAL_ATTEMPT_STATES = {
    AttemptLifecycleState.SUCCEEDED,
    AttemptLifecycleState.FAILED,
    AttemptLifecycleState.CANCELLED,
}


class ExecutionSessionManager:
    """ARI-owned worker leases and recovery preparation for the current backend."""

    def __init__(self, db_path: Path = DB_PATH, *, clock: Clock | None = None) -> None:
        self.ledger = ExecutionLedger(db_path)
        self.db_path = db_path
        self.clock = clock or (lambda: datetime.now(UTC))

    def acquire_lease(
        self,
        *,
        task_id: str,
        attempt_id: str,
        worker_identity: str,
        lease_seconds: int,
        worker_session_ref: str | None = None,
    ) -> WorkerSession:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive.")
        now = self._now()
        expires = now + timedelta(seconds=lease_seconds)
        session_id = f"session-{uuid4()}"
        with self.ledger._transaction() as connection:
            task = self._require_task(connection, task_id)
            self._ensure_task_can_receive_worker(task)
            attempt = self._require_attempt(connection, attempt_id, task_id)
            if attempt["ended_at"] is not None:
                raise ValueError("A terminal attempt cannot acquire a worker lease.")
            if (
                attempt["session_id"] is not None
                and attempt["lease_expires_at"] is not None
                and _parse(str(attempt["lease_expires_at"])) > now
            ):
                raise ValueError("Attempt already has a healthy worker lease.")
            connection.execute(
                """
                update ari_execution_attempts
                set lifecycle_state = ?, session_id = ?, worker_identity = ?,
                    worker_session_ref = ?, lease_started_at = ?, lease_expires_at = ?,
                    last_seen_at = ?, waiting_reason = null
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.ACTIVE,
                    session_id,
                    worker_identity,
                    worker_session_ref,
                    _iso(now),
                    _iso(expires),
                    _iso(now),
                    attempt_id,
                ),
            )
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, active_attempt_id = ?, updated_at = ?,
                    recovery_block_reason = null, row_version = row_version + 1
                where task_id = ?
                """,
                (TaskLifecycleState.ACTIVE, attempt_id, _iso(now), task_id),
            )
            self._insert_event(
                connection,
                task_id=task_id,
                attempt_id=attempt_id,
                event_type="worker.lease_acquired",
                payload={
                    "session_id": session_id,
                    "worker_identity": worker_identity,
                    "lease_expires_at": _iso(expires),
                },
                provenance={"authority": "ari", "operation": "lease_acquisition"},
                now=now,
            )
        return WorkerSession(
            session_id=session_id,
            task_id=task_id,
            attempt_id=attempt_id,
            worker_identity=worker_identity,
            backend_id=str(attempt["backend_id"]),
            state=AttemptLifecycleState.ACTIVE,
            lease=WorkerLease(
                owner=worker_identity,
                started_at=_iso(now),
                expires_at=_iso(expires),
                last_seen_at=_iso(now),
            ),
            prior_attempt_id=attempt["prior_attempt_id"],
        )

    def heartbeat(
        self,
        *,
        attempt_id: str,
        worker_identity: str,
        extend_seconds: int,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerHeartbeat:
        if extend_seconds < 1:
            raise ValueError("extend_seconds must be positive.")
        now = self._now()
        heartbeat_id = f"heartbeat-{uuid4()}"
        with self.ledger._transaction() as connection:
            attempt = self._require_attempt_by_id(connection, attempt_id)
            task = self._require_task(connection, str(attempt["task_id"]))
            self._ensure_task_can_receive_worker(task)
            if attempt["worker_identity"] != worker_identity:
                raise PermissionError("Heartbeat worker does not own this lease.")
            if attempt["session_id"] is None or attempt["lease_expires_at"] is None:
                raise ValueError("Attempt has no active worker lease.")
            if AttemptLifecycleState(attempt["lifecycle_state"]) is not AttemptLifecycleState.ACTIVE:
                raise ValueError("Only an active attempt can heartbeat.")
            current_expiration = _parse(str(attempt["lease_expires_at"]))
            if current_expiration <= now:
                raise ValueError("Expired worker lease cannot be renewed by heartbeat.")
            expires = max(current_expiration, now) + timedelta(seconds=extend_seconds)
            connection.execute(
                """
                update ari_execution_attempts
                set last_seen_at = ?, lease_expires_at = ?
                where attempt_id = ?
                """,
                (_iso(now), _iso(expires), attempt_id),
            )
            connection.execute(
                """
                insert into ari_execution_worker_heartbeats (
                    heartbeat_id, task_id, attempt_id, session_id, lease_owner,
                    observed_at, lease_expires_at, metadata_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    heartbeat_id,
                    attempt["task_id"],
                    attempt_id,
                    attempt["session_id"],
                    worker_identity,
                    _iso(now),
                    _iso(expires),
                    _json(sanitize_payload(metadata or {})),
                ),
            )
            self._insert_event(
                connection,
                task_id=str(attempt["task_id"]),
                attempt_id=attempt_id,
                event_type="worker.heartbeat",
                payload={
                    "heartbeat_id": heartbeat_id,
                    "session_id": attempt["session_id"],
                    "lease_expires_at": _iso(expires),
                },
                provenance={"worker_identity": worker_identity},
                now=now,
            )
        return WorkerHeartbeat(
            heartbeat_id=heartbeat_id,
            task_id=str(attempt["task_id"]),
            attempt_id=attempt_id,
            session_id=str(attempt["session_id"]),
            lease_owner=worker_identity,
            observed_at=_iso(now),
            lease_expires_at=_iso(expires),
        )

    def classify_attempt(self, attempt_id: str) -> AttemptRecoveryDecision:
        attempt = self.ledger._one(
            "select * from ari_execution_attempts where attempt_id = ?", (attempt_id,)
        )
        if attempt is None:
            raise ValueError(f"Execution attempt {attempt_id} does not exist.")
        task = self.ledger.get_task(str(attempt["task_id"]))
        assert task is not None
        task_state = TaskLifecycleState(task["lifecycle_state"])
        if task_state is TaskLifecycleState.WAITING_FOR_WORKER:
            return self._decision(attempt, RecoveryClassification.WAITING_FOR_WORKER, False)
        if task_state is TaskLifecycleState.AWAITING_APPROVAL:
            return self._decision(attempt, RecoveryClassification.AWAITING_APPROVAL, False)
        if task_state is TaskLifecycleState.BLOCKED:
            return self._decision(attempt, RecoveryClassification.BLOCKED, False)
        if task_state is TaskLifecycleState.PAUSED:
            return self._decision(attempt, RecoveryClassification.PAUSED, False)
        if task_state is TaskLifecycleState.CANCELLED:
            return self._decision(attempt, RecoveryClassification.CANCELLED, False)
        attempt_state = AttemptLifecycleState(attempt["lifecycle_state"])
        if attempt_state in _TERMINAL_ATTEMPT_STATES or attempt["ended_at"] is not None:
            return self._decision(attempt, RecoveryClassification.TERMINAL, False)
        if task["latest_checkpoint_id"] is None:
            return self._decision(attempt, RecoveryClassification.UNRECOVERABLE, False)
        if attempt["lease_expires_at"] is None:
            return self._decision(attempt, RecoveryClassification.UNRECOVERABLE, False)
        if _parse(str(attempt["lease_expires_at"])) > self._now():
            return self._decision(attempt, RecoveryClassification.HEALTHY, False)
        return self._decision(attempt, RecoveryClassification.STALE, True)

    def classify_active_attempts(self) -> list[AttemptRecoveryDecision]:
        attempts = self.ledger._many(
            """
            select * from ari_execution_attempts
            where ended_at is null
            order by started_at, rowid
            """,
            (),
        )
        return [self.classify_attempt(str(attempt["attempt_id"])) for attempt in attempts]

    def reconcile_stale_attempt(
        self,
        attempt_id: str,
        *,
        replacement_worker_identity: str,
        lease_seconds: int,
        worker_session_ref: str | None = None,
    ) -> AttemptRecoveryDecision:
        decision = self.classify_attempt(attempt_id)
        if not decision.recoverable:
            return decision
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive.")
        now = self._now()
        expires = now + timedelta(seconds=lease_seconds)
        replacement_attempt_id = f"attempt-{uuid4()}"
        session_id = f"session-{uuid4()}"
        packet_id = f"continuation-{uuid4()}"
        recovery_reason = "Worker lease expired without a timely heartbeat."
        with self.ledger._transaction() as connection:
            old_attempt = self._require_attempt_by_id(connection, attempt_id)
            task = self._require_task(connection, str(old_attempt["task_id"]))
            self._ensure_task_can_recover(task)
            if old_attempt["ended_at"] is not None:
                return self._decision_from_rows(
                    task, old_attempt, RecoveryClassification.TERMINAL, False
                )
            if _parse(str(old_attempt["lease_expires_at"])) > now:
                return self._decision_from_rows(
                    task, old_attempt, RecoveryClassification.HEALTHY, False
                )
            checkpoint = connection.execute(
                "select * from ari_execution_checkpoints where checkpoint_id = ?",
                (task["latest_checkpoint_id"],),
            ).fetchone()
            if checkpoint is None:
                return self._decision_from_rows(
                    task, old_attempt, RecoveryClassification.UNRECOVERABLE, False
                )
            connection.execute(
                """
                update ari_execution_attempts
                set status = 'stale', lifecycle_state = ?, ended_at = ?,
                    failure_json = ?, recovery_json = ?, replacement_attempt_id = ?
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.STALE,
                    _iso(now),
                    _json({"kind": "worker_lost", "reason": recovery_reason}),
                    _json({"recoverable": True, "checkpoint_id": checkpoint["checkpoint_id"]}),
                    replacement_attempt_id,
                    attempt_id,
                ),
            )
            self._insert_event(
                connection,
                task_id=str(task["task_id"]),
                attempt_id=attempt_id,
                event_type="worker.stale",
                payload={
                    "reason": recovery_reason,
                    "lease_expires_at": old_attempt["lease_expires_at"],
                    "last_seen_at": old_attempt["last_seen_at"],
                    "recoverable": True,
                },
                provenance={"authority": "ari", "operation": "lease_reconciliation"},
                now=now,
            )
            self.ledger._insert_attempt(
                connection,
                attempt_id=replacement_attempt_id,
                task_id=str(task["task_id"]),
                executor_id=replacement_worker_identity,
                backend_id=str(old_attempt["backend_id"]),
                model_ref=old_attempt["model_ref"],
                continuation_checkpoint_id=str(checkpoint["checkpoint_id"]),
                provenance={
                    "recovery_reason": recovery_reason,
                    "prior_attempt_id": attempt_id,
                    "checkpoint_id": checkpoint["checkpoint_id"],
                },
                now=_iso(now),
            )
            connection.execute(
                """
                update ari_execution_attempts
                set status = ?, lifecycle_state = ?, session_id = ?, worker_identity = ?,
                    worker_session_ref = ?, lease_started_at = ?, lease_expires_at = ?,
                    last_seen_at = ?, prior_attempt_id = ?, continuation_packet_id = ?,
                    waiting_reason = ?
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    AttemptLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    session_id,
                    replacement_worker_identity,
                    worker_session_ref,
                    _iso(now),
                    _iso(expires),
                    _iso(now),
                    attempt_id,
                    packet_id,
                    "Replacement worker must acknowledge canonical continuation state.",
                    replacement_attempt_id,
                ),
            )
            packet = self._build_packet(
                packet_id=packet_id,
                task=task,
                old_attempt=old_attempt,
                replacement_attempt_id=replacement_attempt_id,
                checkpoint=checkpoint,
                recovery_reason=recovery_reason,
            )
            packet_payload = sanitize_payload(packet.to_dict())
            packet_json = _json(packet_payload)
            connection.execute(
                """
                insert into ari_execution_continuation_packets (
                    packet_id, task_id, attempt_id, prior_attempt_id, checkpoint_id,
                    packet_json, payload_sha256, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    packet_id,
                    task["task_id"],
                    replacement_attempt_id,
                    attempt_id,
                    checkpoint["checkpoint_id"],
                    packet_json,
                    hashlib.sha256(packet_json.encode("utf-8")).hexdigest(),
                    _iso(now),
                ),
            )
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, active_attempt_id = ?, updated_at = ?,
                    recovery_block_reason = ?, row_version = row_version + 1
                where task_id = ?
                """,
                (
                    TaskLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    replacement_attempt_id,
                    _iso(now),
                    "Awaiting replacement worker continuation acknowledgement.",
                    task["task_id"],
                ),
            )
            self._insert_event(
                connection,
                task_id=str(task["task_id"]),
                attempt_id=replacement_attempt_id,
                event_type="recovery.continuation_prepared",
                payload={
                    "prior_attempt_id": attempt_id,
                    "replacement_attempt_id": replacement_attempt_id,
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "packet_id": packet_id,
                },
                provenance={"authority": "ari", "backend_id": old_attempt["backend_id"]},
                now=now,
            )
        return AttemptRecoveryDecision(
            task_id=str(task["task_id"]),
            attempt_id=attempt_id,
            classification=RecoveryClassification.RECOVERABLE,
            reason=recovery_reason,
            recoverable=True,
            latest_checkpoint_id=str(checkpoint["checkpoint_id"]),
            replacement_attempt_id=replacement_attempt_id,
            continuation_packet_id=packet_id,
        )

    def hand_off_to_worker(
        self,
        attempt_id: str,
        *,
        worker_identity: str,
        lease_seconds: int,
        worker_session_ref: str | None = None,
    ) -> AttemptRecoveryDecision:
        """Hand a freshly planned task from ARI's planning attempt to a named worker.

        This is the start-of-task counterpart of `reconcile_stale_attempt`: the planning
        attempt closes as a deliberate handoff (not a worker loss), a worker attempt is
        created under the same task, and the worker receives the same canonical
        continuation packet it must acknowledge before the recovered-action gateway will
        dispatch anything. Restrictions, authority scope, and approval state are copied
        from the canonical checkpoint and never widened.
        """
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive.")
        now = self._now()
        expires = now + timedelta(seconds=lease_seconds)
        worker_attempt_id = f"attempt-{uuid4()}"
        session_id = f"session-{uuid4()}"
        packet_id = f"continuation-{uuid4()}"
        handoff_reason = "ARI handed the planned task to a worker."
        with self.ledger._transaction() as connection:
            planning_attempt = self._require_attempt_by_id(connection, attempt_id)
            task = self._require_task(connection, str(planning_attempt["task_id"]))
            self._ensure_task_can_recover(task)
            if TaskLifecycleState(task["lifecycle_state"]) not in {
                TaskLifecycleState.WAITING_FOR_WORKER,
                TaskLifecycleState.ACTIVE,
            }:
                raise ValueError(
                    f"Task state {task['lifecycle_state']} cannot be handed to a worker."
                )
            if task["active_attempt_id"] != attempt_id:
                raise ValueError("Only the task's active attempt can hand off to a worker.")
            if planning_attempt["ended_at"] is not None:
                raise ValueError("A terminal attempt cannot hand off to a worker.")
            checkpoint = connection.execute(
                "select * from ari_execution_checkpoints where checkpoint_id = ?",
                (task["latest_checkpoint_id"],),
            ).fetchone()
            if checkpoint is None:
                raise ValueError("Task has no canonical checkpoint for a worker handoff.")
            connection.execute(
                """
                update ari_execution_attempts
                set status = 'handed_off', lifecycle_state = ?, ended_at = ?,
                    recovery_json = ?, replacement_attempt_id = ?
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.SUCCEEDED,
                    _iso(now),
                    _json({"handoff": True, "checkpoint_id": checkpoint["checkpoint_id"]}),
                    worker_attempt_id,
                    attempt_id,
                ),
            )
            self.ledger._insert_attempt(
                connection,
                attempt_id=worker_attempt_id,
                task_id=str(task["task_id"]),
                executor_id=worker_identity,
                backend_id=str(planning_attempt["backend_id"]),
                model_ref=planning_attempt["model_ref"],
                continuation_checkpoint_id=str(checkpoint["checkpoint_id"]),
                provenance={
                    "handoff_reason": handoff_reason,
                    "prior_attempt_id": attempt_id,
                    "checkpoint_id": checkpoint["checkpoint_id"],
                },
                now=_iso(now),
            )
            connection.execute(
                """
                update ari_execution_attempts
                set status = ?, lifecycle_state = ?, session_id = ?, worker_identity = ?,
                    worker_session_ref = ?, lease_started_at = ?, lease_expires_at = ?,
                    last_seen_at = ?, prior_attempt_id = ?, continuation_packet_id = ?,
                    waiting_reason = ?
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    AttemptLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    session_id,
                    worker_identity,
                    worker_session_ref,
                    _iso(now),
                    _iso(expires),
                    _iso(now),
                    attempt_id,
                    packet_id,
                    "Worker must acknowledge canonical task state.",
                    worker_attempt_id,
                ),
            )
            packet = self._build_packet(
                packet_id=packet_id,
                task=task,
                old_attempt=planning_attempt,
                replacement_attempt_id=worker_attempt_id,
                checkpoint=checkpoint,
                recovery_reason=handoff_reason,
            )
            packet_json = _json(sanitize_payload(packet.to_dict()))
            connection.execute(
                """
                insert into ari_execution_continuation_packets (
                    packet_id, task_id, attempt_id, prior_attempt_id, checkpoint_id,
                    packet_json, payload_sha256, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    packet_id,
                    task["task_id"],
                    worker_attempt_id,
                    attempt_id,
                    checkpoint["checkpoint_id"],
                    packet_json,
                    hashlib.sha256(packet_json.encode("utf-8")).hexdigest(),
                    _iso(now),
                ),
            )
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, active_attempt_id = ?, updated_at = ?,
                    recovery_block_reason = ?, row_version = row_version + 1
                where task_id = ?
                """,
                (
                    TaskLifecycleState.AWAITING_CONTINUATION_ACKNOWLEDGEMENT,
                    worker_attempt_id,
                    _iso(now),
                    "Awaiting worker acknowledgement of canonical task state.",
                    task["task_id"],
                ),
            )
            self._insert_event(
                connection,
                task_id=str(task["task_id"]),
                attempt_id=worker_attempt_id,
                event_type="worker.handoff_prepared",
                payload={
                    "planning_attempt_id": attempt_id,
                    "worker_attempt_id": worker_attempt_id,
                    "worker_identity": worker_identity,
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "packet_id": packet_id,
                },
                provenance={"authority": "ari", "operation": "worker_handoff"},
                now=now,
            )
        return AttemptRecoveryDecision(
            task_id=str(task["task_id"]),
            attempt_id=attempt_id,
            classification=RecoveryClassification.HEALTHY,
            reason=handoff_reason,
            recoverable=False,
            latest_checkpoint_id=str(checkpoint["checkpoint_id"]),
            replacement_attempt_id=worker_attempt_id,
            continuation_packet_id=packet_id,
        )

    def acknowledge_continuation(
        self,
        *,
        packet_id: str,
        worker_identity: str,
        acknowledgement: ContinuationAcknowledgement,
    ) -> dict[str, Any]:
        now = self._now()
        acknowledgement_id = f"ack-{uuid4()}"
        clean_ack = sanitize_payload(acknowledgement.to_dict())
        with self.ledger._transaction() as connection:
            packet_row = connection.execute(
                "select * from ari_execution_continuation_packets where packet_id = ?",
                (packet_id,),
            ).fetchone()
            if packet_row is None:
                raise ValueError(f"Continuation packet {packet_id} does not exist.")
            packet = json.loads(packet_row["packet_json"])
            attempt = self._require_attempt(
                connection, str(packet_row["attempt_id"]), str(packet_row["task_id"])
            )
            if attempt["worker_identity"] != worker_identity:
                raise PermissionError("Acknowledgement worker does not own replacement session.")
            self._validate_acknowledgement(packet, clean_ack)
            acknowledgement_json = _json(clean_ack)
            connection.execute(
                """
                insert into ari_execution_continuation_acknowledgements (
                    acknowledgement_id, packet_id, task_id, attempt_id, worker_identity,
                    acknowledgement_json, payload_sha256, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acknowledgement_id,
                    packet_id,
                    packet_row["task_id"],
                    packet_row["attempt_id"],
                    worker_identity,
                    acknowledgement_json,
                    hashlib.sha256(acknowledgement_json.encode("utf-8")).hexdigest(),
                    _iso(now),
                ),
            )
            connection.execute(
                """
                update ari_execution_attempts
                set status = ?, lifecycle_state = ?, continuation_acknowledgement_id = ?,
                    waiting_reason = ?
                where attempt_id = ?
                """,
                (
                    AttemptLifecycleState.EXECUTION_READY,
                    AttemptLifecycleState.EXECUTION_READY,
                    acknowledgement_id,
                    "Automatic side-effect resume is disabled pending authority/tool gateway.",
                    packet_row["attempt_id"],
                ),
            )
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, active_attempt_id = ?, updated_at = ?,
                    recovery_block_reason = ?, row_version = row_version + 1
                where task_id = ?
                """,
                (
                    TaskLifecycleState.EXECUTION_READY,
                    packet_row["attempt_id"],
                    _iso(now),
                    "Automatic side-effect resume is disabled pending authority/tool gateway.",
                    packet_row["task_id"],
                ),
            )
            self._insert_event(
                connection,
                task_id=str(packet_row["task_id"]),
                attempt_id=str(packet_row["attempt_id"]),
                event_type="continuation.acknowledged",
                payload={
                    "packet_id": packet_id,
                    "acknowledgement_id": acknowledgement_id,
                    "next_proposed_action": clean_ack["next_proposed_action"],
                },
                provenance={"worker_identity": worker_identity, "authority": "ari"},
                now=now,
            )
        stored = self.ledger._one(
            """
            select * from ari_execution_continuation_acknowledgements
            where acknowledgement_id = ?
            """,
            (acknowledgement_id,),
        )
        assert stored is not None
        return stored

    def set_task_lifecycle(
        self,
        task_id: str,
        state: TaskLifecycleState,
        *,
        reason: str,
    ) -> None:
        if state not in {
            TaskLifecycleState.AWAITING_APPROVAL,
            TaskLifecycleState.PAUSED,
            TaskLifecycleState.CANCELLED,
            TaskLifecycleState.BLOCKED,
        }:
            raise ValueError("This operation only applies an explicit recovery gate.")
        now = self._now()
        with self.ledger._transaction() as connection:
            task = self._require_task(connection, task_id)
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, pause_reason = ?, cancel_reason = ?,
                    recovery_block_reason = ?, updated_at = ?, row_version = row_version + 1
                where task_id = ?
                """,
                (
                    state,
                    reason if state is TaskLifecycleState.PAUSED else task["pause_reason"],
                    reason if state is TaskLifecycleState.CANCELLED else task["cancel_reason"],
                    reason,
                    _iso(now),
                    task_id,
                ),
            )
            self._insert_event(
                connection,
                task_id=task_id,
                attempt_id=str(task["active_attempt_id"]),
                event_type=f"task.{state}",
                payload={"reason": reason},
                provenance={"authority": "ari"},
                now=now,
            )

    def inspect_task(self, task_id: str) -> dict[str, Any] | None:
        bundle = self.ledger.get_task_bundle(task_id)
        if bundle is None:
            return None
        task = bundle["task"]
        attempt_id = task.get("active_attempt_id")
        active_attempt = next(
            (item for item in bundle["attempts"] if item["attempt_id"] == attempt_id),
            None,
        )
        classification = None
        if active_attempt is not None:
            classification = self.classify_attempt(str(active_attempt["attempt_id"]))
        packet = self.ledger._one(
            """
            select * from ari_execution_continuation_packets
            where task_id = ? order by rowid desc limit 1
            """,
            (task_id,),
        )
        acknowledgement = self.ledger._one(
            """
            select * from ari_execution_continuation_acknowledgements
            where task_id = ? order by rowid desc limit 1
            """,
            (task_id,),
        )
        latest_checkpoint = bundle["checkpoints"][-1] if bundle["checkpoints"] else None
        next_action = (
            packet["packet"].get("recommended_next_action")
            if packet is not None
            else None if latest_checkpoint is None else latest_checkpoint["next_recommended_action"]
        )
        bundle["session"] = {
            "active_attempt_id": attempt_id,
            "active_attempt": active_attempt,
            "lease_classification": (
                None if classification is None else classification.classification
            ),
            "lease_healthy": (
                classification is not None
                and classification.classification is RecoveryClassification.HEALTHY
            ),
            "last_heartbeat_at": (
                None if active_attempt is None else active_attempt["last_seen_at"]
            ),
            "continuation_packet": packet,
            "continuation_acknowledgement": acknowledgement,
            "next_action": next_action,
            "execution_resumed": False,
            "resume_blocked_reason": task.get("recovery_block_reason"),
        }
        from .gateway import RecoveredActionGateway

        gateway_inspection = RecoveredActionGateway(
            self.db_path,
            clock=self.clock,
        ).inspect_task(task_id)
        bundle["recovered_action_gateway"] = gateway_inspection
        bundle["session"]["execution_resumed"] = any(
            execution.get("started_at") is not None
            for execution in gateway_inspection["executions"]
        )
        return bundle

    def _decision(
        self,
        attempt: dict[str, Any],
        classification: RecoveryClassification,
        recoverable: bool,
    ) -> AttemptRecoveryDecision:
        task = self.ledger.get_task(str(attempt["task_id"]))
        assert task is not None
        return AttemptRecoveryDecision(
            task_id=str(attempt["task_id"]),
            attempt_id=str(attempt["attempt_id"]),
            classification=classification,
            reason=self._classification_reason(classification),
            recoverable=recoverable,
            latest_checkpoint_id=task["latest_checkpoint_id"],
        )

    @staticmethod
    def _decision_from_rows(
        task: sqlite3.Row,
        attempt: sqlite3.Row,
        classification: RecoveryClassification,
        recoverable: bool,
    ) -> AttemptRecoveryDecision:
        return AttemptRecoveryDecision(
            task_id=str(task["task_id"]),
            attempt_id=str(attempt["attempt_id"]),
            classification=classification,
            reason=ExecutionSessionManager._classification_reason(classification),
            recoverable=recoverable,
            latest_checkpoint_id=task["latest_checkpoint_id"],
        )

    @staticmethod
    def _classification_reason(classification: RecoveryClassification) -> str:
        reasons = {
            RecoveryClassification.HEALTHY: "Worker lease is healthy.",
            RecoveryClassification.WAITING_FOR_WORKER: "Task is waiting for a worker lease.",
            RecoveryClassification.STALE: "Worker lease expired and is recoverable.",
            RecoveryClassification.TERMINAL: "Attempt is already terminal.",
            RecoveryClassification.AWAITING_APPROVAL: "Task is awaiting approval.",
            RecoveryClassification.BLOCKED: "Task is blocked by policy or authority.",
            RecoveryClassification.PAUSED: "Task was explicitly paused.",
            RecoveryClassification.CANCELLED: "Task was cancelled.",
            RecoveryClassification.RECOVERABLE: "A replacement session is prepared.",
            RecoveryClassification.UNRECOVERABLE: "Canonical recovery state is incomplete.",
        }
        return reasons[classification]

    @staticmethod
    def _build_packet(
        *,
        packet_id: str,
        task: sqlite3.Row,
        old_attempt: sqlite3.Row,
        replacement_attempt_id: str,
        checkpoint: sqlite3.Row,
        recovery_reason: str,
    ) -> ContinuationPacket:
        return ContinuationPacket(
            packet_id=packet_id,
            task_id=str(task["task_id"]),
            attempt_id=replacement_attempt_id,
            prior_attempt_id=str(old_attempt["attempt_id"]),
            checkpoint_id=str(checkpoint["checkpoint_id"]),
            objective=str(checkpoint["objective"]),
            success_criteria=tuple(_load_json(checkpoint["success_criteria_json"])),
            current_plan=_load_json(checkpoint["current_plan_json"]),
            completed_steps=tuple(_load_json(checkpoint["completed_steps_json"])),
            pending_steps=tuple(_load_json(checkpoint["pending_steps_json"])),
            important_findings=tuple(_load_json(checkpoint["important_findings_json"])),
            assumptions=tuple(_load_json(checkpoint["assumptions_json"])),
            decisions=tuple(_load_json(checkpoint["decisions_json"])),
            artifacts=tuple(_load_json(checkpoint["artifacts_json"])),
            actions_taken=tuple(_load_json(checkpoint["actions_taken_json"])),
            verification_results=tuple(
                _load_json(checkpoint["verification_results_json"])
            ),
            restrictions=tuple(_load_json(checkpoint["restrictions_json"])),
            authority_scope=_load_json(checkpoint["authority_scope_json"]),
            approval_state=_load_json(checkpoint["approval_state_json"]),
            authority_snapshot_ref=checkpoint["authority_snapshot_ref"],
            authority_snapshot_hash=checkpoint["authority_snapshot_hash"],
            prior_attempt_provenance=_load_json(old_attempt["provenance_json"]),
            recovery_reason=recovery_reason,
            recommended_next_action=checkpoint["next_recommended_action"],
        )

    @staticmethod
    def _validate_acknowledgement(
        packet: dict[str, Any], acknowledgement: dict[str, Any]
    ) -> None:
        exact_fields = {
            "objective": "objective",
            "completed_steps": "completed_steps",
            "pending_steps": "pending_steps",
            "authority_scope": "authority_scope",
            "authority_snapshot_ref": "authority_snapshot_ref",
            "next_proposed_action": "recommended_next_action",
        }
        for acknowledgement_key, packet_key in exact_fields.items():
            if acknowledgement[acknowledgement_key] != packet[packet_key]:
                raise ValueError(
                    f"Continuation acknowledgement does not match {acknowledgement_key}."
                )
        packet_restrictions = set(packet["restrictions"])
        acknowledged_restrictions = set(acknowledgement["restrictions"])
        if not packet_restrictions.issubset(acknowledged_restrictions):
            raise ValueError("Continuation acknowledgement would widen authority restrictions.")

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Execution session clock must return timezone-aware datetimes.")
        return value.astimezone(UTC)

    @staticmethod
    def _require_task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        return ExecutionLedger._require_task(connection, task_id)

    @staticmethod
    def _require_attempt(
        connection: sqlite3.Connection, attempt_id: str, task_id: str
    ) -> sqlite3.Row:
        attempt = connection.execute(
            "select * from ari_execution_attempts where attempt_id = ? and task_id = ?",
            (attempt_id, task_id),
        ).fetchone()
        if attempt is None:
            raise ValueError(f"Attempt {attempt_id} does not belong to task {task_id}.")
        return attempt

    @staticmethod
    def _require_attempt_by_id(
        connection: sqlite3.Connection, attempt_id: str
    ) -> sqlite3.Row:
        attempt = connection.execute(
            "select * from ari_execution_attempts where attempt_id = ?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            raise ValueError(f"Execution attempt {attempt_id} does not exist.")
        return attempt

    @staticmethod
    def _ensure_task_can_receive_worker(task: sqlite3.Row) -> None:
        state = TaskLifecycleState(task["lifecycle_state"])
        if state in {
            TaskLifecycleState.AWAITING_APPROVAL,
            TaskLifecycleState.PAUSED,
            TaskLifecycleState.CANCELLED,
            TaskLifecycleState.BLOCKED,
        }:
            raise ValueError(f"Task state {state} cannot acquire or renew a worker lease.")

    @staticmethod
    def _ensure_task_can_recover(task: sqlite3.Row) -> None:
        ExecutionSessionManager._ensure_task_can_receive_worker(task)
        if task["latest_checkpoint_id"] is None:
            raise ValueError("Task has no canonical checkpoint for recovery.")

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        attempt_id: str,
        event_type: str,
        payload: dict[str, Any],
        provenance: dict[str, Any],
        now: datetime,
    ) -> None:
        sequence = ExecutionLedger._next_sequence(
            connection, "ari_execution_events", task_id
        )
        connection.execute(
            """
            insert into ari_execution_events (
                event_id, task_id, attempt_id, sequence, event_type,
                payload_json, provenance_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"event-{uuid4()}",
                task_id,
                attempt_id,
                sequence,
                event_type,
                _json(sanitize_payload(payload)),
                _json(sanitize_payload(provenance)),
                _iso(now),
            ),
        )


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _load_json(value: str) -> Any:
    return json.loads(value)
