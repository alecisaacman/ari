from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.paths import DB_PATH
from .contracts import (
    ActionIdempotencyState,
    AttemptLifecycleState,
    EffectReconciliationOutcome,
    EffectReconciliationResult,
    EvidenceIndication,
    ReconciliationEvidence,
    TaskLifecycleState,
)
from .gateway import RecoveredActionGateway, _iso, _parse
from .ledger import ExecutionLedger, _decode_row, _json, sanitize_payload

Clock = Callable[[], datetime]
TransactionHook = Callable[[str], None]

# States whose external effect ARI cannot prove either way. `executing` qualifies only
# once its reserving attempt is superseded; see `_effective_state`.
RECONCILABLE_STATES = frozenset(
    {
        ActionIdempotencyState.EFFECT_UNCERTAIN,
        ActionIdempotencyState.VERIFICATION_FAILED,
    }
)
_TERMINAL_TASK_STATES = frozenset(
    {
        TaskLifecycleState.SUCCEEDED,
        TaskLifecycleState.FAILED,
        TaskLifecycleState.CANCELLED,
    }
)
# Gates that are not worker failures; an expired lease under them does not make the
# attempt stale (mirrors ExecutionSessionManager.classify_attempt).
_NON_WORKER_GATES = frozenset(
    {
        TaskLifecycleState.WAITING_FOR_WORKER,
        TaskLifecycleState.AWAITING_APPROVAL,
        TaskLifecycleState.BLOCKED,
        TaskLifecycleState.PAUSED,
    }
)
_RESULTING_STATE = {
    EffectReconciliationOutcome.EFFECT_CONFIRMED: ActionIdempotencyState.EFFECT_CONFIRMED,
    EffectReconciliationOutcome.EFFECT_CONFIRMED_ABSENT: (
        ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
    ),
}


class ReconciliationRefused(ValueError):
    """The reconciliation request was refused and nothing was persisted."""


class EffectReconciler:
    """Records durable, auditable truth about one uncertain external effect.

    Reconciliation never dispatches an action. It only changes what ARI knows about
    one exact persisted execution: that its effect occurred, that it provably did not,
    or that the evidence is still inconclusive.
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        *,
        clock: Clock | None = None,
        transaction_hook: TransactionHook | None = None,
    ) -> None:
        self.ledger = ExecutionLedger(db_path)
        self.db_path = db_path
        self.clock = clock or (lambda: datetime.now(UTC))
        self.transaction_hook = transaction_hook

    def reconcile(
        self,
        *,
        task_id: str,
        attempt_id: str,
        execution_id: str,
        action_id: str,
        action_digest: str,
        outcome: EffectReconciliationOutcome | str,
        evidence: Sequence[ReconciliationEvidence | dict[str, Any]],
        reconciled_by: str,
        reason: str,
        provenance: dict[str, Any] | None = None,
    ) -> EffectReconciliationResult:
        requested = self._requested_outcome(outcome)
        items = self._normalize_evidence(evidence)
        if not isinstance(reconciled_by, str) or not reconciled_by.strip():
            raise ReconciliationRefused("reconciled_by is required.")
        if not isinstance(reason, str) or not reason.strip():
            raise ReconciliationRefused("A reconciliation reason is required.")
        clean_evidence = sanitize_payload([item.to_dict() for item in items])
        evidence_sha256 = hashlib.sha256(_json(clean_evidence).encode("utf-8")).hexdigest()
        request_key = self._request_key(
            task_id=task_id,
            execution_id=execution_id,
            action_id=action_id,
            action_digest=action_digest,
            outcome=requested,
            evidence_sha256=evidence_sha256,
            reconciled_by=reconciled_by,
            reason=reason,
        )
        now = self._now()
        try:
            with self.ledger._transaction() as connection:
                existing = connection.execute(
                    "select * from ari_execution_effect_reconciliations where request_key = ?",
                    (request_key,),
                ).fetchone()
                if existing is not None:
                    return self._result(_decode_row(existing), duplicate=True)
                return self._apply(
                    connection,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    execution_id=execution_id,
                    action_id=action_id,
                    action_digest=action_digest,
                    requested=requested,
                    items=items,
                    clean_evidence=clean_evidence,
                    evidence_sha256=evidence_sha256,
                    request_key=request_key,
                    reconciled_by=reconciled_by,
                    reason=reason,
                    provenance=provenance,
                    now=now,
                )
        except sqlite3.IntegrityError as error:
            raise ReconciliationRefused(
                f"Reconciliation conflicted with concurrent canonical state: {error}"
            ) from error

    def list_reconciliations(self, task_id: str) -> list[dict[str, Any]]:
        return self.ledger._many(
            """
            select * from ari_execution_effect_reconciliations
            where task_id = ? order by rowid
            """,
            (task_id,),
        )

    def _apply(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        attempt_id: str,
        execution_id: str,
        action_id: str,
        action_digest: str,
        requested: EffectReconciliationOutcome,
        items: tuple[ReconciliationEvidence, ...],
        clean_evidence: list[dict[str, Any]],
        evidence_sha256: str,
        request_key: str,
        reconciled_by: str,
        reason: str,
        provenance: dict[str, Any] | None,
        now: datetime,
    ) -> EffectReconciliationResult:
        task = connection.execute(
            "select * from ari_execution_tasks where task_id = ?", (task_id,)
        ).fetchone()
        if task is None:
            raise ReconciliationRefused(f"Execution task {task_id} does not exist.")
        if TaskLifecycleState(task["lifecycle_state"]) in _TERMINAL_TASK_STATES:
            raise ReconciliationRefused(
                f"Task lifecycle is {task['lifecycle_state']}; terminal tasks are not reconciled."
            )
        if task["active_attempt_id"] is None or task["active_attempt_id"] != attempt_id:
            raise ReconciliationRefused(
                "Only the task's active attempt may reconcile canonical execution state."
            )
        attempt = connection.execute(
            "select * from ari_execution_attempts where attempt_id = ?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            raise ReconciliationRefused(f"Attempt {attempt_id} does not exist.")
        lease_expired = attempt["lease_expires_at"] is not None and (
            _parse(str(attempt["lease_expires_at"])) <= now
        )
        if attempt["lifecycle_state"] == AttemptLifecycleState.STALE or (
            lease_expired
            and TaskLifecycleState(task["lifecycle_state"]) not in _NON_WORKER_GATES
        ):
            raise ReconciliationRefused(
                "The active attempt is stale; recover the worker session before reconciling."
            )
        row = connection.execute(
            "select * from ari_execution_action_executions where execution_id = ?",
            (execution_id,),
        ).fetchone()
        if row is None:
            raise ReconciliationRefused(f"Action execution {execution_id} does not exist.")
        execution = _decode_row(row)
        if (
            execution["task_id"] != task_id
            or execution["action_id"] != action_id
            or execution["action_digest"] != action_digest
        ):
            raise ReconciliationRefused(
                "The execution record does not match the requested task, action, and digest."
            )
        stored = ActionIdempotencyState(execution["state"])
        # Effective state is judged against the canonical active attempt: an `executing`
        # row whose reserving attempt is still active may be mid-dispatch right now.
        effective = RecoveredActionGateway._effective_state(execution, str(attempt_id))
        if effective is ActionIdempotencyState.EXECUTING:
            raise ReconciliationRefused(
                "The action is still executing under the active attempt; it cannot be "
                "reconciled while it may be in flight."
            )
        if effective not in RECONCILABLE_STATES:
            raise ReconciliationRefused(
                f"Execution state {effective} is not eligible for reconciliation."
            )
        outcome, assessment = self._assess(requested, items)
        transitioned = outcome is not EffectReconciliationOutcome.INCONCLUSIVE
        resulting = _RESULTING_STATE[outcome] if transitioned else effective
        reconciliation_id = f"effect-reconciliation-{uuid4()}"
        basis = RecoveredActionGateway._checkpoint_in(connection, str(task["latest_checkpoint_id"]))
        self._hook("validated")
        clean_provenance = sanitize_payload(
            provenance or {"authority": "ari", "operation": "effect_reconciliation"}
        )
        connection.execute(
            """
            insert into ari_execution_effect_reconciliations (
                reconciliation_id, request_key, execution_id, task_id, attempt_id,
                reserving_attempt_id, decision_id, action_id, action_digest,
                idempotency_key, requested_outcome, outcome, previous_state,
                effective_previous_state, resulting_state, retry_eligible, reconciled_by,
                reason, assessment, evidence_json, evidence_sha256, basis_checkpoint_id,
                checkpoint_id, provenance_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                null, ?, ?)
            """,
            (
                reconciliation_id,
                request_key,
                execution_id,
                task_id,
                attempt_id,
                execution["attempt_id"],
                execution["decision_id"],
                action_id,
                action_digest,
                execution["idempotency_key"],
                requested,
                outcome,
                stored,
                effective,
                resulting,
                int(outcome is EffectReconciliationOutcome.EFFECT_CONFIRMED_ABSENT),
                reconciled_by,
                reason,
                assessment,
                _json(clean_evidence),
                evidence_sha256,
                basis["checkpoint_id"],
                _json(clean_provenance),
                _iso(now),
            ),
        )
        self._hook("record_inserted")
        event_payload = {
            "reconciliation_id": reconciliation_id,
            "execution_id": execution_id,
            "action_id": action_id,
            "requested_outcome": requested,
            "outcome": outcome,
            "previous_state": stored,
            "resulting_state": resulting,
            "reconciled_by": reconciled_by,
            "assessment": assessment,
            "evidence_sha256": evidence_sha256,
        }
        if not transitioned:
            RecoveredActionGateway._insert_event(
                connection,
                task_id=task_id,
                attempt_id=attempt_id,
                event_type="action.effect_reconciliation_inconclusive",
                payload=event_payload,
                provenance=clean_provenance,
                now=now,
            )
            self._hook("event_inserted")
            stored_record = self._record_in(connection, reconciliation_id)
            return self._result(stored_record, duplicate=False)

        # Compare-and-swap on the exact stored state: a concurrent transition, a late
        # report, or a gateway write in between makes this update match nothing.
        updated = connection.execute(
            """
            update ari_execution_action_executions
            set state = ?, effect_status = ?, reconciliation_id = ?, updated_at = ?
            where execution_id = ? and state = ?
            """,
            (
                resulting,
                f"{outcome}_by_reconciliation",
                reconciliation_id,
                _iso(now),
                execution_id,
                stored,
            ),
        )
        if updated.rowcount != 1:
            raise ReconciliationRefused(
                "The execution state changed during reconciliation; nothing was recorded."
            )
        self._hook("execution_updated")
        checkpoint_id = self._insert_reconciliation_checkpoint(
            connection,
            basis,
            task_id=task_id,
            attempt_id=attempt_id,
            action_id=action_id,
            execution_id=execution_id,
            reconciliation_id=reconciliation_id,
            outcome=outcome,
            event_payload=event_payload,
            now=now,
        )
        connection.execute(
            """
            update ari_execution_effect_reconciliations set checkpoint_id = ?
            where reconciliation_id = ?
            """,
            (checkpoint_id, reconciliation_id),
        )
        self._hook("checkpoint_inserted")
        return self._result(self._record_in(connection, reconciliation_id), duplicate=False)

    def _insert_reconciliation_checkpoint(
        self,
        connection: sqlite3.Connection,
        basis: dict[str, Any],
        *,
        task_id: str,
        attempt_id: str,
        action_id: str,
        execution_id: str,
        reconciliation_id: str,
        outcome: EffectReconciliationOutcome,
        event_payload: dict[str, Any],
        now: datetime,
    ) -> str:
        pending = [*basis["pending_steps"]]
        completed = [*basis["completed_steps"]]
        if outcome is EffectReconciliationOutcome.EFFECT_CONFIRMED:
            remaining = [step for step in pending if step.get("action_id") != action_id]
            for step in pending:
                if step.get("action_id") == action_id:
                    completed.append(
                        {
                            **step,
                            "verified": False,
                            "reconciled": True,
                            "reconciliation_id": reconciliation_id,
                        }
                    )
                    break
            pending = remaining
            if pending:
                next_action = pending[0].get("reason")
            else:
                next_action = "No pending action remains; ARI must decide final task disposition."
        else:
            next_action = (
                f"The effect of {action_id} is confirmed absent; a retry requires an explicit "
                "canonical plan revision and a new ARI resume decision."
            )
        state = RecoveredActionGateway._checkpoint_state(
            basis,
            completed_steps=completed,
            pending_steps=pending,
            decisions=[
                *basis["decisions"],
                {
                    "decision": "effect_reconciled",
                    "reconciliation_id": reconciliation_id,
                    "execution_id": execution_id,
                    "action_id": action_id,
                    "outcome": outcome,
                },
            ],
            next_recommended_action=next_action,
        )
        checkpoint_id = f"checkpoint-{uuid4()}"
        ExecutionLedger._insert_boundary(
            connection,
            checkpoint_id=checkpoint_id,
            event_id=f"event-{uuid4()}",
            task_id=task_id,
            attempt_id=attempt_id,
            trigger="effect_reconciled",
            event_type="action.effect_reconciled",
            state_payload=sanitize_payload(asdict(state)),
            event_payload=sanitize_payload(event_payload),
            idempotency_key=f"effect-reconciliation:{reconciliation_id}",
            now=_iso(now),
        )
        return checkpoint_id

    @staticmethod
    def _assess(
        requested: EffectReconciliationOutcome,
        items: tuple[ReconciliationEvidence, ...],
    ) -> tuple[EffectReconciliationOutcome, str]:
        """Decide what the evidence actually supports; doubt resolves to inconclusive.

        Confirmation needs at least one present observation and no absent one.
        Confirmed absence opens a future retry path, so every observation must
        indicate absence and at least one must cite a verifiable reference.
        """
        indications = {item.indicates for item in items}
        inconclusive = EffectReconciliationOutcome.INCONCLUSIVE
        if requested is EffectReconciliationOutcome.INCONCLUSIVE:
            return inconclusive, "Recorded as inconclusive at the requester's direction."
        if requested is EffectReconciliationOutcome.EFFECT_CONFIRMED:
            if EvidenceIndication.EFFECT_ABSENT in indications:
                return inconclusive, "Evidence is contradictory: an observation indicates absence."
            if EvidenceIndication.EFFECT_PRESENT not in indications:
                return inconclusive, "Insufficient evidence: no observation shows the effect."
            return requested, "Evidence shows the effect occurred and none contradicts it."
        if EvidenceIndication.EFFECT_PRESENT in indications:
            return inconclusive, "Evidence is contradictory: an observation indicates the effect."
        if indications != {EvidenceIndication.EFFECT_ABSENT}:
            return inconclusive, "Insufficient evidence: not every observation shows absence."
        if not any(item.reference for item in items):
            return (
                inconclusive,
                "Insufficient evidence: confirmed absence requires a verifiable reference.",
            )
        return requested, "Every observation shows the effect is absent, with a reference."

    @staticmethod
    def _requested_outcome(outcome: EffectReconciliationOutcome | str) -> EffectReconciliationOutcome:
        try:
            return EffectReconciliationOutcome(outcome)
        except ValueError as error:
            raise ReconciliationRefused(f"Unknown reconciliation outcome {outcome!r}.") from error

    @staticmethod
    def _normalize_evidence(
        evidence: Sequence[ReconciliationEvidence | dict[str, Any]],
    ) -> tuple[ReconciliationEvidence, ...]:
        if isinstance(evidence, (str, bytes, dict)) or not isinstance(evidence, Sequence):
            raise ReconciliationRefused("Evidence must be a sequence of observations.")
        if not evidence:
            raise ReconciliationRefused("At least one evidence observation is required.")
        try:
            return tuple(ReconciliationEvidence.from_value(item) for item in evidence)
        except ValueError as error:
            raise ReconciliationRefused(f"Malformed evidence: {error}") from error

    @staticmethod
    def _request_key(**material: Any) -> str:
        digest = hashlib.sha256(_json(material).encode("utf-8")).hexdigest()
        return f"effect-reconciliation-request:{digest}"

    @staticmethod
    def _record_in(connection: sqlite3.Connection, reconciliation_id: str) -> dict[str, Any]:
        row = connection.execute(
            "select * from ari_execution_effect_reconciliations where reconciliation_id = ?",
            (reconciliation_id,),
        ).fetchone()
        assert row is not None
        return _decode_row(row)

    @staticmethod
    def _result(record: dict[str, Any], *, duplicate: bool) -> EffectReconciliationResult:
        outcome = EffectReconciliationOutcome(record["outcome"])
        return EffectReconciliationResult(
            reconciliation_id=str(record["reconciliation_id"]),
            task_id=str(record["task_id"]),
            execution_id=str(record["execution_id"]),
            action_id=str(record["action_id"]),
            attempt_id=str(record["attempt_id"]),
            requested_outcome=EffectReconciliationOutcome(record["requested_outcome"]),
            outcome=outcome,
            previous_state=ActionIdempotencyState(record["effective_previous_state"]),
            resulting_state=ActionIdempotencyState(record["resulting_state"]),
            transitioned=outcome is not EffectReconciliationOutcome.INCONCLUSIVE,
            duplicate=duplicate,
            retry_eligible=bool(record["retry_eligible"]),
            assessment=str(record["assessment"]),
            checkpoint_id=record["checkpoint_id"],
        )

    def _hook(self, stage: str) -> None:
        if self.transaction_hook is not None:
            self.transaction_hook(stage)

    def _now(self) -> datetime:
        return RecoveredActionGateway._normalize_time(self.clock())
