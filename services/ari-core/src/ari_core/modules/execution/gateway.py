from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.paths import DB_PATH
from ...core.pause import get_pause_state
from .command_capabilities import CommandClass
from .contracts import (
    ActionIdempotencyState,
    AttemptLifecycleState,
    CheckpointState,
    RecoveredActionProposal,
    RecoveredActionResumeResult,
    ResumeDecision,
    TaskLifecycleState,
)
from .dispatch import (
    DispatchFences,
    LockIdentity,
    TerminalityClassifier,
    classify_effect_terminality,
    unbounded_terminality,
)
from .executor import execute_action, verify_action_result
from .ledger import ExecutionLedger, _decode_row, _json, sanitize_payload
from .sandbox import DISPATCH_HOLD_FDS, ExecutionRoot
from .tools import ExecutionToolRegistry, get_execution_tool_registry

# Restrictions under which a recovered action may not mutate anything.
NO_MUTATION_RESTRICTIONS = frozenset({"read only", "read-only", "no file writes", "no mutations"})

Clock = Callable[[], datetime]
PauseStateReader = Callable[[], dict[str, Any]]
ActionExecutor = Callable[[dict[str, Any], Path | str | None], dict[str, Any]]
BeforeExecuteHook = Callable[[RecoveredActionProposal], None]

_SUPERSEDED_REASON = (
    "The attempt was superseded while the action ran; its result is recorded as evidence "
    "only and the effect requires reconciliation before any retry."
)
_RECONCILED_STATES = frozenset(
    {
        ActionIdempotencyState.EFFECT_CONFIRMED,
        ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT,
    }
)
# States of another action in the same task that block every dispatch in the task:
# ARI cannot tell whether a differently named action repeats that action's effect.
_UNRESOLVED_STATES = frozenset(
    {
        ActionIdempotencyState.AUTHORIZED_NOT_RUN,
        ActionIdempotencyState.EXECUTING,
        ActionIdempotencyState.EFFECT_UNCERTAIN,
        ActionIdempotencyState.VERIFICATION_FAILED,
    }
)
_TASK_EXECUTIONS = """
    select e.*, f.state as dispatch_fence_state,
        f.landing_token as fence_landing_token,
        r.redispatch_safe as reconciliation_redispatch_safe,
        r.landing_token as reconciliation_landing_token
    from ari_execution_action_executions e
    left join ari_execution_dispatch_fences f on f.execution_id = e.execution_id
    left join ari_execution_effect_reconciliations r
        on r.reconciliation_id = e.reconciliation_id
    where e.task_id = ?
    order by e.rowid desc
"""


class _ReservationConflict(ValueError):
    """The action could not be reserved because canonical state moved or it is governed."""

    def __init__(self, reason: str, state: ActionIdempotencyState) -> None:
        super().__init__(reason)
        self.reason = reason
        self.state = state


class RecoveredActionGateway:
    """The single ARI authority boundary for one recovered pending action."""

    def __init__(
        self,
        db_path: Path = DB_PATH,
        *,
        execution_root: Path | str | None = None,
        clock: Clock | None = None,
        pause_state_reader: PauseStateReader | None = None,
        tool_registry: ExecutionToolRegistry | None = None,
        action_executor: ActionExecutor | None = None,
        before_execute_hook: BeforeExecuteHook | None = None,
        effect_terminality: TerminalityClassifier | None = None,
    ) -> None:
        self.ledger = ExecutionLedger(db_path)
        self.db_path = db_path
        self.execution_root = ExecutionRoot(execution_root)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.pause_state_reader = pause_state_reader or get_pause_state
        self.tool_registry = tool_registry or get_execution_tool_registry()
        self.action_executor = action_executor or execute_action
        # Only the built-in executor's effects are known; an injected executor must
        # declare its own classification or is treated as unbounded.
        if effect_terminality is None:
            effect_terminality = (
                classify_effect_terminality
                if self.action_executor is execute_action
                else unbounded_terminality
            )
        self.effect_terminality = effect_terminality
        self.before_execute_hook = before_execute_hook
        self.dispatch_fences = DispatchFences(db_path, clock=self.clock)

    def propose_next_action(
        self,
        *,
        task_id: str,
        attempt_id: str,
    ) -> RecoveredActionProposal:
        task = self.ledger.get_task(task_id)
        if task is None:
            raise ValueError(f"Execution task {task_id} does not exist.")
        attempt = self.ledger._one(
            "select * from ari_execution_attempts where attempt_id = ? and task_id = ?",
            (attempt_id, task_id),
        )
        if attempt is None:
            raise ValueError(f"Attempt {attempt_id} does not belong to task {task_id}.")
        if task["latest_checkpoint_id"] is None:
            raise ValueError("Recovered task has no canonical checkpoint.")
        checkpoint = self.ledger.get_checkpoint(str(task["latest_checkpoint_id"]))
        if checkpoint is None:
            raise ValueError("Recovered task has no canonical checkpoint.")

        pending_steps = checkpoint["pending_steps"]
        if not isinstance(pending_steps, list):
            raise ValueError("Canonical checkpoint pending steps are malformed.")
        if not pending_steps:
            previous = self._latest_action_execution(task_id)
            if previous is None:
                raise ValueError("Recovered task has no pending action to resume.")
            decision = self.ledger._one(
                "select * from ari_execution_resume_decisions where decision_id = ?",
                (str(previous["decision_id"]),),
            )
            if decision is None:
                raise ValueError("Recorded action execution has no resume decision.")
            return self._proposal_from_decision(
                decision,
                ActionIdempotencyState.ALREADY_COMPLETED,
                attempt_id=attempt_id,
            )

        pending = pending_steps[0]
        if not isinstance(pending, dict) or not str(pending.get("action_id") or "").strip():
            raise ValueError("Canonical pending action is malformed: action_id is required.")
        action_id = str(pending["action_id"])
        current_plan = checkpoint["current_plan"]
        plan_actions = current_plan.get("actions", []) if isinstance(current_plan, dict) else None
        if not isinstance(plan_actions, list):
            raise ValueError("Canonical plan actions are malformed.")
        planned_action = next(
            (
                item
                for item in plan_actions
                if isinstance(item, dict) and str(item.get("id")) == action_id
            ),
            None,
        )
        if planned_action is None:
            raise ValueError(f"Pending action {action_id} is absent from the canonical plan.")
        payload = planned_action.get("payload", {})
        execution_action = planned_action.get("execution_action")
        if not isinstance(payload, dict) or not (
            execution_action is None or isinstance(execution_action, dict)
        ):
            raise ValueError(f"Pending action {action_id} has a malformed payload.")
        proposed_action = dict(
            execution_action or {"type": planned_action.get("action_type"), **payload}
        )
        if not isinstance(proposed_action.get("type"), str) or not proposed_action["type"]:
            raise ValueError(f"Pending action {action_id} has no action type.")
        target_resources = self._target_resources(proposed_action)
        action_digest = self._action_digest(
            proposed_action,
            target_resources,
            checkpoint.get("authority_snapshot_hash"),
        )
        idempotency_key = self._idempotency_key(task_id, action_id, action_digest)
        governing = self._governing_execution(
            task_id=task_id,
            action_id=action_id,
            idempotency_key=idempotency_key,
            attempt_id=attempt_id,
        )
        idempotency_state = self._idempotency_state(governing, checkpoint)
        approval_required = bool(planned_action.get("requires_approval")) or bool(
            checkpoint["approval_state"].get("required", False)
        )
        approval = self._find_approval(
            task_id=task_id,
            action_digest=action_digest,
            target_resources=target_resources,
            authority_snapshot_hash=checkpoint.get("authority_snapshot_hash"),
            include_expired=True,
        )
        acknowledged_restrictions: list[str] = []
        acknowledgement_id = attempt.get("continuation_acknowledgement_id")
        if acknowledgement_id is not None:
            acknowledgement = self.ledger._one(
                """
                select * from ari_execution_continuation_acknowledgements
                where acknowledgement_id = ?
                """,
                (str(acknowledgement_id),),
            )
            if acknowledgement is not None:
                acknowledged_restrictions = list(
                    acknowledgement["acknowledgement"].get("restrictions", [])
                )
        restrictions = tuple(
            dict.fromkeys([*checkpoint["restrictions"], *acknowledged_restrictions])
        )
        return RecoveredActionProposal(
            task_id=task_id,
            attempt_id=attempt_id,
            checkpoint_id=str(checkpoint["checkpoint_id"]),
            action_id=action_id,
            proposed_action=proposed_action,
            action_digest=action_digest,
            target_resources=target_resources,
            authority_snapshot_ref=checkpoint.get("authority_snapshot_ref"),
            authority_snapshot_hash=checkpoint.get("authority_snapshot_hash"),
            authority_scope=dict(checkpoint["authority_scope"]),
            approval_required=approval_required,
            approval_reference=None if approval is None else str(approval["approval_id"]),
            restrictions=restrictions,
            idempotency_key=idempotency_key,
            idempotency_state=idempotency_state,
            provenance={
                "authority": "ari",
                "operation": "recovered_action_proposal",
                "prior_attempt_id": attempt.get("prior_attempt_id"),
                "continuation_packet_id": attempt.get("continuation_packet_id"),
            },
        )

    def approve_next_action(
        self,
        *,
        task_id: str,
        attempt_id: str,
        approved_by: str,
        reason: str,
        expires_at: datetime | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not approved_by.strip():
            raise ValueError("approved_by is required.")
        proposal = self.propose_next_action(task_id=task_id, attempt_id=attempt_id)
        if proposal.idempotency_state is not ActionIdempotencyState.NEVER_ATTEMPTED:
            raise ValueError("Only a never-attempted pending action can receive approval.")
        now = self._now()
        expiration = None if expires_at is None else self._normalize_time(expires_at)
        if expiration is not None and expiration <= now:
            raise ValueError("Approval expiration must be in the future.")
        approval_id = f"action-approval-{uuid4()}"
        with self.ledger._transaction() as connection:
            connection.execute(
                """
                insert into ari_execution_action_approvals (
                    approval_id, task_id, attempt_id, checkpoint_id, action_id,
                    action_digest, target_resources_json, authority_snapshot_ref,
                    authority_snapshot_hash, status, approved_by, reason, expires_at,
                    provenance_json, created_at, resolved_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    task_id,
                    attempt_id,
                    proposal.checkpoint_id,
                    proposal.action_id,
                    proposal.action_digest,
                    _json(proposal.target_resources),
                    proposal.authority_snapshot_ref,
                    proposal.authority_snapshot_hash,
                    approved_by,
                    reason,
                    None if expiration is None else _iso(expiration),
                    _json(
                        sanitize_payload(
                            provenance
                            or {"authority": "alec", "operation": "action_approval"}
                        )
                    ),
                    _iso(now),
                    _iso(now),
                ),
            )
            task = self._require_task(connection, task_id)
            if task["active_attempt_id"] == attempt_id and task["lifecycle_state"] == (
                TaskLifecycleState.AWAITING_APPROVAL
            ):
                connection.execute(
                    """
                    update ari_execution_tasks
                    set lifecycle_state = ?, recovery_block_reason = null, updated_at = ?,
                        row_version = row_version + 1
                    where task_id = ?
                    """,
                    (TaskLifecycleState.EXECUTION_READY, _iso(now), task_id),
                )
                connection.execute(
                    """
                    update ari_execution_attempts
                    set lifecycle_state = ?, status = ?, waiting_reason = null
                    where attempt_id = ?
                    """,
                    (
                        AttemptLifecycleState.EXECUTION_READY,
                        AttemptLifecycleState.EXECUTION_READY,
                        attempt_id,
                    ),
                )
            self._insert_event(
                connection,
                task_id=task_id,
                attempt_id=attempt_id,
                event_type="action.approved",
                payload={
                    "approval_id": approval_id,
                    "action_id": proposal.action_id,
                    "action_digest": proposal.action_digest,
                    "target_resources": proposal.target_resources,
                    "expires_at": None if expiration is None else _iso(expiration),
                },
                provenance={"authority": "ari", "approved_by": approved_by},
                now=now,
            )
        stored = self.ledger._one(
            "select * from ari_execution_action_approvals where approval_id = ?",
            (approval_id,),
        )
        assert stored is not None
        return stored

    def resume_one(
        self,
        *,
        task_id: str,
        attempt_id: str,
        worker_identity: str,
        session_id: str,
        provenance: dict[str, Any] | None = None,
    ) -> RecoveredActionResumeResult:
        proposal = self.propose_next_action(task_id=task_id, attempt_id=attempt_id)
        if proposal.idempotency_state is not ActionIdempotencyState.NEVER_ATTEMPTED:
            return self._deny_duplicate(proposal, provenance=provenance)

        decision, reason, approval_reference = self._evaluate_gate(
            proposal,
            worker_identity=worker_identity,
            session_id=session_id,
        )
        if decision is not ResumeDecision.ALLOW:
            decision_id = self._persist_decision(
                proposal,
                decision=decision,
                reason=reason,
                approval_reference=approval_reference,
                provenance=provenance,
            )
            self._apply_denied_lifecycle(proposal, decision, reason)
            denial_checkpoint = self._record_denial_checkpoint(
                proposal,
                decision_id=decision_id,
                decision=decision,
                reason=reason,
            )
            return self._result(
                proposal,
                decision_id=decision_id,
                decision=decision,
                reason=reason,
                executed=False,
                idempotency_state=ActionIdempotencyState.NEVER_ATTEMPTED,
                approval_reference=approval_reference,
                result_checkpoint_id=denial_checkpoint,
            )

        try:
            decision_id, execution_id, pre_checkpoint = self._authorize_and_reserve(
                proposal,
                reason=reason,
                approval_reference=approval_reference,
                provenance=provenance,
            )
        except _ReservationConflict as conflict:
            conflict_decision_id = self._persist_decision(
                proposal,
                decision=ResumeDecision.DENY,
                reason=conflict.reason,
                approval_reference=approval_reference,
                provenance=provenance,
            )
            return self._result(
                proposal,
                decision_id=conflict_decision_id,
                decision=ResumeDecision.DENY,
                reason=conflict.reason,
                executed=False,
                idempotency_state=conflict.state,
                approval_reference=approval_reference,
            )

        if self.before_execute_hook is not None:
            self.before_execute_hook(proposal)

        # The dispatched action must be exactly the reserved action. Anything else stops
        # before effect; a changed action needs its own decision and reservation.
        try:
            refreshed = self.propose_next_action(task_id=task_id, attempt_id=attempt_id)
        except ValueError as error:
            refreshed_error: str | None = (
                f"Canonical pending action could not be re-derived before dispatch: {error}"
            )
        else:
            refreshed_error = (
                None
                if refreshed.idempotency_key == proposal.idempotency_key
                else "The canonical pending action changed after authorization; the reserved "
                "action will not be dispatched."
            )
        if refreshed_error is not None:
            return self._stop_before_effect(
                proposal,
                execution_id,
                decision=ResumeDecision.DENY,
                reason=refreshed_error,
                approval_reference=approval_reference,
                provenance=provenance,
                pre_checkpoint_id=pre_checkpoint,
            )
        late_decision, late_reason, late_approval = self._evaluate_gate(
            refreshed,
            worker_identity=worker_identity,
            session_id=session_id,
        )
        if late_decision is not ResumeDecision.ALLOW:
            return self._stop_before_effect(
                refreshed,
                execution_id,
                decision=late_decision,
                reason=late_reason,
                approval_reference=late_approval,
                provenance=provenance,
                pre_checkpoint_id=pre_checkpoint,
            )

        # The logical action's dispatch lock is held from the final authority check,
        # through the effect, until the dispatch is recorded as returned. While it is
        # held, no landing proof for this dispatch can succeed and no other dispatcher
        # of the same action can take it.
        lock = self.dispatch_fences.lock_for(refreshed.task_id, refreshed.action_id)
        if not lock.try_acquire():
            return self._stop_before_effect(
                refreshed,
                execution_id,
                decision=ResumeDecision.BLOCKED,
                reason=f"The logical action's dispatch lock was not acquired: {lock.refusal}",
                approval_reference=late_approval,
                provenance=provenance,
                pre_checkpoint_id=pre_checkpoint,
            )
        failure: dict[str, Any] | None = None
        try:
            try:
                assert lock.identity is not None
                fence_id = self._mark_executing(
                    execution_id,
                    refreshed,
                    lock=lock.identity,
                    worker_identity=worker_identity,
                    session_id=session_id,
                    approval_reference=late_approval,
                )
            except ValueError as error:
                return self._stop_before_effect(
                    refreshed,
                    execution_id,
                    decision=ResumeDecision.BLOCKED,
                    reason=str(error),
                    approval_reference=late_approval,
                    provenance=provenance,
                    pre_checkpoint_id=pre_checkpoint,
                )

            # Dispatch boundary: from here on the side effect may have occurred, so
            # every failure path records uncertainty instead of permitting a retry.
            # Subprocesses inherit the lock, but a descendant can drop it: that is why
            # a subprocess effect is unbounded and its return proves nothing.
            assert lock.fd is not None
            inherited = DISPATCH_HOLD_FDS.set((lock.fd,))
            try:
                action_result = self.action_executor(
                    refreshed.proposed_action,
                    self.execution_root.root,
                )
            except Exception as error:  # noqa: BLE001 - uncertainty must be durable
                failure = {"type": type(error).__name__, "message": str(error)}
                self.dispatch_fences.mark_returned(fence_id, outcome={"error": failure})
            else:
                self.dispatch_fences.mark_returned(fence_id, outcome={"result": action_result})
            finally:
                DISPATCH_HOLD_FDS.reset(inherited)
        finally:
            lock.release()

        if failure is not None:
            failure_checkpoint = self._persist_uncertain(refreshed, execution_id, error=failure)
            return self._result(
                refreshed,
                decision_id=decision_id,
                decision=ResumeDecision.ALLOW,
                reason="Action execution raised after dispatch; side-effect outcome is uncertain.",
                executed=True,
                idempotency_state=ActionIdempotencyState.EFFECT_UNCERTAIN,
                approval_reference=late_approval,
                pre_checkpoint_id=pre_checkpoint,
                result_checkpoint_id=failure_checkpoint,
            )

        result_checkpoint = self._persist_result(refreshed, execution_id, action_result)
        if result_checkpoint is None:
            return self._superseded_result(
                refreshed,
                decision_id=decision_id,
                approval_reference=late_approval,
                pre_checkpoint_id=pre_checkpoint,
                action_result=action_result,
            )

        verification = verify_action_result(
            refreshed.proposed_action,
            action_result,
            self.execution_root.root,
        )
        verified = bool(verification["verified"])
        final_state = (
            ActionIdempotencyState.SUCCEEDED
            if verified
            else ActionIdempotencyState.VERIFICATION_FAILED
        )
        verification_checkpoint = self._persist_verification(
            refreshed,
            execution_id,
            action_result=action_result,
            verification=verification,
            final_state=final_state,
        )
        if verification_checkpoint is None:
            return self._superseded_result(
                refreshed,
                decision_id=decision_id,
                approval_reference=late_approval,
                pre_checkpoint_id=pre_checkpoint,
                action_result=action_result,
                verification=verification,
            )
        return self._result(
            refreshed,
            decision_id=decision_id,
            decision=ResumeDecision.ALLOW,
            reason=(
                "ARI authorized, executed, and verified exactly one recovered action."
                if verified
                else "The action ran but verification failed; it will not be retried blindly."
            ),
            executed=True,
            idempotency_state=final_state,
            approval_reference=late_approval,
            pre_checkpoint_id=pre_checkpoint,
            result_checkpoint_id=result_checkpoint,
            verification_checkpoint_id=verification_checkpoint,
            result=action_result,
            verification=verification,
        )

    def inspect_task(self, task_id: str) -> dict[str, Any]:
        decisions = self.ledger._many(
            """
            select * from ari_execution_resume_decisions
            where task_id = ? order by rowid
            """,
            (task_id,),
        )
        executions = self.ledger._many(
            """
            select * from ari_execution_action_executions
            where task_id = ? order by rowid
            """,
            (task_id,),
        )
        approvals = self.ledger._many(
            """
            select * from ari_execution_action_approvals
            where task_id = ? order by rowid
            """,
            (task_id,),
        )
        fences = self.ledger._many(
            """
            select * from ari_execution_dispatch_fences
            where task_id = ? order by rowid
            """,
            (task_id,),
        )
        task = self.ledger.get_task(task_id)
        if task is None:
            raise ValueError(f"Execution task {task_id} does not exist.")
        proposal = None
        attempt_id = task.get("active_attempt_id")
        if attempt_id is not None:
            try:
                proposal = self.propose_next_action(
                    task_id=task_id,
                    attempt_id=str(attempt_id),
                ).to_dict()
            except ValueError:
                proposal = None
        return {
            "proposed_action": proposal,
            "latest_decision": decisions[-1] if decisions else None,
            "latest_execution": executions[-1] if executions else None,
            "latest_approval": approvals[-1] if approvals else None,
            "decisions": decisions,
            "executions": executions,
            "approvals": approvals,
            "dispatch_fences": fences,
            "redispatch_safety": [
                {
                    "execution_id": row["execution_id"],
                    "action_id": row["action_id"],
                    "state": row["state"],
                    "dispatch_fence_state": row["dispatch_fence_state"],
                    "landing_ruled_out": row["fence_landing_token"] is not None,
                    "safe_to_redispatch": self._safe_to_redispatch(
                        row, ActionIdempotencyState(row["state"])
                    ),
                }
                for row in reversed(self.ledger._many(_TASK_EXECUTIONS, (task_id,)))
            ],
            "one_action_limit": True,
            "stop_reason": (
                "Control returned to ARI after one action; another explicit resume decision is "
                "required for any remaining pending action."
            ),
        }

    def _evaluate_gate(
        self,
        proposal: RecoveredActionProposal,
        *,
        worker_identity: str,
        session_id: str,
    ) -> tuple[ResumeDecision, str, str | None]:
        pause_state = self.pause_state_reader()
        if bool(pause_state.get("paused")):
            return (
                ResumeDecision.BLOCKED,
                f"Global execution pause is active: {pause_state.get('reason') or 'no reason given'}.",
                None,
            )
        task = self.ledger.get_task(proposal.task_id)
        attempt = self.ledger._one(
            "select * from ari_execution_attempts where attempt_id = ? and task_id = ?",
            (proposal.attempt_id, proposal.task_id),
        )
        checkpoint = self.ledger.get_checkpoint(proposal.checkpoint_id)
        if task is None or attempt is None or checkpoint is None:
            return ResumeDecision.DENY, "Canonical task, attempt, or checkpoint is missing.", None
        task_state = TaskLifecycleState(task["lifecycle_state"])
        if task_state is TaskLifecycleState.AWAITING_APPROVAL:
            return ResumeDecision.REQUIRE_APPROVAL, "Task is awaiting action-bound approval.", None
        if task_state is TaskLifecycleState.PAUSED:
            return ResumeDecision.BLOCKED, "Task is paused.", None
        if task_state is TaskLifecycleState.CANCELLED:
            return ResumeDecision.DENY, "Task is cancelled.", None
        if task_state is TaskLifecycleState.BLOCKED:
            return ResumeDecision.BLOCKED, "Task is blocked by policy or authority.", None
        if task_state is not TaskLifecycleState.EXECUTION_READY:
            return (
                ResumeDecision.DENY,
                f"Task lifecycle is {task_state}; execution_ready is required.",
                None,
            )
        if task["active_attempt_id"] != proposal.attempt_id:
            return ResumeDecision.DENY, "Attempt has been superseded by a newer active attempt.", None
        if AttemptLifecycleState(attempt["lifecycle_state"]) is not (
            AttemptLifecycleState.EXECUTION_READY
        ):
            return ResumeDecision.DENY, "Attempt is not execution_ready.", None
        if attempt["worker_identity"] != worker_identity or attempt["session_id"] != session_id:
            return ResumeDecision.DENY, "Worker or session identity does not own the active lease.", None
        if attempt["lease_expires_at"] is None or _parse(str(attempt["lease_expires_at"])) <= (
            self._now()
        ):
            return ResumeDecision.DENY, "Worker lease is stale.", None
        if attempt["continuation_acknowledgement_id"] is None:
            return ResumeDecision.DENY, "Replacement worker has not acknowledged continuation.", None
        acknowledgement = self.ledger._one(
            """
            select * from ari_execution_continuation_acknowledgements
            where acknowledgement_id = ? and attempt_id = ?
            """,
            (attempt["continuation_acknowledgement_id"], proposal.attempt_id),
        )
        if acknowledgement is None:
            return ResumeDecision.DENY, "Continuation acknowledgement is missing.", None
        packet = self.ledger._one(
            "select * from ari_execution_continuation_packets where packet_id = ?",
            (str(attempt["continuation_packet_id"]),),
        )
        if packet is None:
            return ResumeDecision.DENY, "Continuation packet is missing.", None
        packet_payload = packet["packet"]
        if (
            task.get("authority_snapshot_ref") != proposal.authority_snapshot_ref
            or task.get("authority_snapshot_hash") != proposal.authority_snapshot_hash
            or packet_payload.get("authority_snapshot_ref") != proposal.authority_snapshot_ref
            or packet_payload.get("authority_snapshot_hash") != proposal.authority_snapshot_hash
        ):
            return ResumeDecision.BLOCKED, "Authority snapshot changed during recovery.", None
        if task["authority_scope"] != proposal.authority_scope or (
            packet_payload.get("authority_scope") != proposal.authority_scope
        ):
            return ResumeDecision.BLOCKED, "Authority scope changed during recovery.", None
        if task["approval_state"] != checkpoint["approval_state"] or (
            packet_payload.get("approval_state") != checkpoint["approval_state"]
        ):
            return ResumeDecision.BLOCKED, "Approval requirements changed during recovery.", None
        canonical_restrictions = set(proposal.restrictions)
        required_restrictions = set(task["restrictions"]) | set(
            packet_payload.get("restrictions", [])
        )
        if not required_restrictions.issubset(canonical_restrictions):
            return ResumeDecision.BLOCKED, "Task restrictions were weakened during recovery.", None
        validation_error = self.tool_registry.validate_execution_action(
            proposal.proposed_action,
            execution_root=self.execution_root,
        )
        if validation_error is not None:
            return ResumeDecision.BLOCKED, validation_error, None
        restriction_error = self._restriction_error(proposal)
        if restriction_error is not None:
            return ResumeDecision.BLOCKED, restriction_error, None
        scope_error = self._scope_error(proposal)
        if scope_error is not None:
            return ResumeDecision.BLOCKED, scope_error, None
        approval = self._find_approval(
            task_id=proposal.task_id,
            action_digest=proposal.action_digest,
            target_resources=proposal.target_resources,
            authority_snapshot_hash=proposal.authority_snapshot_hash,
            include_expired=True,
        )
        if proposal.approval_required:
            if approval is None:
                return (
                    ResumeDecision.REQUIRE_APPROVAL,
                    "No approval is bound to this action digest and target resources.",
                    None,
                )
            if approval["expires_at"] is not None and _parse(str(approval["expires_at"])) <= (
                self._now()
            ):
                return (
                    ResumeDecision.REQUIRE_APPROVAL,
                    "The action-bound approval has expired.",
                    str(approval["approval_id"]),
                )
            if approval["status"] != "approved":
                return (
                    ResumeDecision.REQUIRE_APPROVAL,
                    f"Action approval status is {approval['status']}.",
                    str(approval["approval_id"]),
                )
        return (
            ResumeDecision.ALLOW,
            "All ARI lifecycle, authority, approval, idempotency, and sandbox gates passed.",
            None if approval is None else str(approval["approval_id"]),
        )

    def _restriction_error(self, proposal: RecoveredActionProposal) -> str | None:
        action_type = str(proposal.proposed_action.get("type") or "")
        normalized = {item.strip().lower().replace("_", " ") for item in proposal.restrictions}
        no_mutation = bool(normalized.intersection(NO_MUTATION_RESTRICTIONS))
        if action_type in {"write_file", "patch_file"} and no_mutation:
            return "Task restrictions prohibit file mutation."
        if action_type == "run_command" and "no command execution" in normalized:
            return "Task restrictions prohibit command execution."
        if action_type == "run_command" and no_mutation:
            command_class = self.tool_registry.command_class(
                proposal.proposed_action,
                execution_root=self.execution_root,
            )
            # Commands are potentially mutating by default; only explicit read-only
            # inspection capabilities satisfy a no-mutation restriction.
            if command_class is not CommandClass.READ_ONLY_INSPECTION:
                return (
                    "Task restrictions prohibit mutation; only read-only inspection "
                    "commands (ls, cat) may run, and this command executes code."
                )
        if "no network" in normalized and action_type not in self.tool_registry.allowed_action_types():
            return "Task restrictions prohibit unclassified network-capable actions."
        return None

    def _scope_error(self, proposal: RecoveredActionProposal) -> str | None:
        action_type = str(proposal.proposed_action.get("type") or "")
        permitted = proposal.authority_scope.get("permitted_side_effects")
        if permitted is not None and action_type not in set(permitted):
            return f"Authority scope does not permit {action_type}."
        denied = set(proposal.authority_scope.get("denied_action_types", []))
        if action_type in denied:
            return f"Authority scope explicitly denies {action_type}."
        filesystem_scope = proposal.authority_scope.get("filesystem")
        path = proposal.proposed_action.get("path")
        if filesystem_scope is not None and path is not None:
            try:
                resolved = self.execution_root.resolve_path(str(path))
                relative = str(resolved.relative_to(self.execution_root.root))
            except ValueError as error:
                return str(error)
            if not any(
                relative == str(item).rstrip("/")
                or relative.startswith(f"{str(item).rstrip('/')}/")
                for item in filesystem_scope
            ):
                return f"Target resource is outside the task authority scope: {relative}"
        return None

    def _authorize_and_reserve(
        self,
        proposal: RecoveredActionProposal,
        *,
        reason: str,
        approval_reference: str | None,
        provenance: dict[str, Any] | None,
    ) -> tuple[str, str, str]:
        """Persist the allow decision, idempotency reservation, and pre-action checkpoint.

        All three commit in one immediate transaction, after re-checking that the
        canonical checkpoint and active attempt the gate evaluated are still current and
        that no other execution governs this action.
        """
        now = self._now()
        decision_id = f"resume-decision-{uuid4()}"
        execution_id = f"action-execution-{uuid4()}"
        with self.ledger._transaction() as connection:
            task = self._require_task(connection, proposal.task_id)
            if (
                task["latest_checkpoint_id"] != proposal.checkpoint_id
                or task["active_attempt_id"] != proposal.attempt_id
            ):
                raise _ReservationConflict(
                    "Canonical checkpoint or active attempt changed after the gate decision; "
                    "the action was not reserved.",
                    ActionIdempotencyState.NEVER_ATTEMPTED,
                )
            rows = [
                _decode_row(row)
                for row in connection.execute(_TASK_EXECUTIONS, (proposal.task_id,)).fetchall()
            ]
            governing = self._select_governing(
                rows,
                action_id=proposal.action_id,
                idempotency_key=proposal.idempotency_key,
                attempt_id=proposal.attempt_id,
            )
            if governing is not None:
                execution, state = governing
                raise _ReservationConflict(
                    self._governing_reason(proposal.action_id, execution, state), state
                )
            self._insert_decision(
                connection,
                proposal,
                decision_id=decision_id,
                decision=ResumeDecision.ALLOW,
                reason=reason,
                approval_reference=approval_reference,
                provenance=provenance,
                now=now,
            )
            connection.execute(
                """
                insert into ari_execution_action_executions (
                    execution_id, decision_id, task_id, attempt_id, action_id,
                    action_digest, idempotency_key, state, effect_status,
                    evidence_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, 'not_started', '{}', ?, ?)
                """,
                (
                    execution_id,
                    decision_id,
                    proposal.task_id,
                    proposal.attempt_id,
                    proposal.action_id,
                    proposal.action_digest,
                    proposal.idempotency_key,
                    ActionIdempotencyState.AUTHORIZED_NOT_RUN,
                    _iso(now),
                    _iso(now),
                ),
            )
            DispatchFences.issue(
                connection,
                execution_id=execution_id,
                task_id=proposal.task_id,
                action_id=proposal.action_id,
                idempotency_key=proposal.idempotency_key,
                attempt_id=proposal.attempt_id,
                effect_terminality=self.effect_terminality(proposal.proposed_action),
                now=_iso(now),
            )
            checkpoint = self._checkpoint_in(connection, proposal.checkpoint_id)
            pre_checkpoint_id = self._insert_checkpoint(
                connection,
                proposal,
                trigger="before_authorized_action",
                event_type="action.pre_checkpointed",
                state=self._checkpoint_state(
                    checkpoint,
                    decisions=[
                        *checkpoint["decisions"],
                        {
                            "decision_id": decision_id,
                            "decision": ResumeDecision.ALLOW,
                            "action_id": proposal.action_id,
                            "action_digest": proposal.action_digest,
                            "approval_reference": approval_reference,
                        },
                    ],
                    restrictions=proposal.restrictions,
                    next_recommended_action=(
                        f"Execute only {proposal.action_id}, then return to ARI."
                    ),
                ),
                event_payload={
                    "decision_id": decision_id,
                    "action_id": proposal.action_id,
                    "action_digest": proposal.action_digest,
                    "idempotency_key": proposal.idempotency_key,
                },
                idempotency_key=f"{proposal.idempotency_key}:pre-action",
                now=now,
            )
            self._set_execution(
                connection,
                execution_id,
                now=now,
                pre_checkpoint_id=pre_checkpoint_id,
            )
        return decision_id, execution_id, pre_checkpoint_id

    def _persist_decision(
        self,
        proposal: RecoveredActionProposal,
        *,
        decision: ResumeDecision,
        reason: str,
        approval_reference: str | None,
        provenance: dict[str, Any] | None,
    ) -> str:
        decision_id = f"resume-decision-{uuid4()}"
        now = self._now()
        with self.ledger._transaction() as connection:
            self._insert_decision(
                connection,
                proposal,
                decision_id=decision_id,
                decision=decision,
                reason=reason,
                approval_reference=approval_reference,
                provenance=provenance,
                now=now,
            )
        return decision_id

    def _insert_decision(
        self,
        connection: sqlite3.Connection,
        proposal: RecoveredActionProposal,
        *,
        decision_id: str,
        decision: ResumeDecision,
        reason: str,
        approval_reference: str | None,
        provenance: dict[str, Any] | None,
        now: datetime,
    ) -> None:
        clean_provenance = sanitize_payload(
            provenance
            or {"authority": "ari", "operation": "recovered_action_resume_decision"}
        )
        connection.execute(
            """
            insert into ari_execution_resume_decisions (
                decision_id, task_id, attempt_id, checkpoint_id, action_id,
                proposed_action_json, action_digest, target_resources_json,
                authority_snapshot_ref, authority_snapshot_hash, authority_scope_json,
                approval_reference, restrictions_json, idempotency_key, decision,
                reason, provenance_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                proposal.task_id,
                proposal.attempt_id,
                proposal.checkpoint_id,
                proposal.action_id,
                _json(sanitize_payload(proposal.proposed_action)),
                proposal.action_digest,
                _json(proposal.target_resources),
                proposal.authority_snapshot_ref,
                proposal.authority_snapshot_hash,
                _json(proposal.authority_scope),
                approval_reference,
                _json(proposal.restrictions),
                proposal.idempotency_key,
                decision,
                reason,
                _json(clean_provenance),
                _iso(now),
            ),
        )
        self._insert_event(
            connection,
            task_id=proposal.task_id,
            attempt_id=proposal.attempt_id,
            event_type="action.resume_decided",
            payload={
                "decision_id": decision_id,
                "decision": decision,
                "reason": reason,
                "action_id": proposal.action_id,
                "action_digest": proposal.action_digest,
                "idempotency_key": proposal.idempotency_key,
                "approval_reference": approval_reference,
            },
            provenance=clean_provenance,
            now=now,
        )

    def _persist_result(
        self,
        proposal: RecoveredActionProposal,
        execution_id: str,
        action_result: dict[str, Any],
    ) -> str | None:
        """Atomically persist the raw result and its checkpoint.

        Returns None when the attempt no longer owns the execution; the result is then
        kept only as evidence and the effect is recorded as uncertain.
        """
        now = self._now()
        with self.ledger._transaction() as connection:
            if not self._owns_execution(connection, proposal, execution_id):
                if self._late_evidence_after_reconciliation(
                    connection, proposal, execution_id, now=now, result=action_result
                ):
                    return None
                self._set_execution(
                    connection,
                    execution_id,
                    now=now,
                    state=ActionIdempotencyState.EFFECT_UNCERTAIN,
                    effect_status="result_recorded_after_supersession",
                    result=action_result,
                    error={"reason": _SUPERSEDED_REASON},
                    finished_at=now,
                )
                return None
            checkpoint = self._latest_checkpoint_in(connection, proposal.task_id)
            checkpoint_id = self._insert_checkpoint(
                connection,
                proposal,
                trigger="action_result_persisted",
                event_type="action.result_persisted",
                state=self._checkpoint_state(
                    checkpoint,
                    actions_taken=[
                        *checkpoint["actions_taken"],
                        {
                            "action_id": proposal.action_id,
                            "action_digest": proposal.action_digest,
                            "result": sanitize_payload(action_result),
                            "idempotency_key": proposal.idempotency_key,
                        },
                    ],
                    next_recommended_action=f"Verify {proposal.action_id} before completion.",
                ),
                event_payload={"action_id": proposal.action_id, "result": action_result},
                idempotency_key=f"{proposal.idempotency_key}:result",
                now=now,
            )
            self._set_execution(
                connection,
                execution_id,
                now=now,
                effect_status="result_recorded",
                result=action_result,
                result_checkpoint_id=checkpoint_id,
            )
        return checkpoint_id

    def _persist_verification(
        self,
        proposal: RecoveredActionProposal,
        execution_id: str,
        *,
        action_result: dict[str, Any],
        verification: dict[str, Any],
        final_state: ActionIdempotencyState,
    ) -> str | None:
        """Atomically checkpoint verification and finalize the execution record.

        Completing the pending step and marking the reservation succeeded commit
        together, so a crash cannot leave a completed step with an executing record.
        """
        now = self._now()
        verified = bool(verification["verified"])
        with self.ledger._transaction() as connection:
            if not self._owns_execution(connection, proposal, execution_id):
                if self._late_evidence_after_reconciliation(
                    connection,
                    proposal,
                    execution_id,
                    now=now,
                    result=action_result,
                    verification=verification,
                ):
                    return None
                self._set_execution(
                    connection,
                    execution_id,
                    now=now,
                    state=ActionIdempotencyState.EFFECT_UNCERTAIN,
                    effect_status="result_recorded_after_supersession",
                    verification=verification,
                    evidence=dict(verification["evidence"]),
                    error={"reason": _SUPERSEDED_REASON},
                    finished_at=now,
                )
                return None
            checkpoint = self._latest_checkpoint_in(connection, proposal.task_id)
            pending = [*checkpoint["pending_steps"]]
            completed = [*checkpoint["completed_steps"]]
            errors = [*checkpoint["errors"]]
            artifacts = [*checkpoint["artifacts"]]
            if verified:
                if pending and pending[0].get("action_id") == proposal.action_id:
                    step = pending.pop(0)
                else:
                    step = {
                        "action_id": proposal.action_id,
                        "action_type": proposal.proposed_action["type"],
                    }
                completed.append({**step, "verified": True})
                if proposal.proposed_action["type"] in {"write_file", "patch_file"}:
                    artifacts.append(
                        {
                            **dict(verification["evidence"]),
                            "action_id": proposal.action_id,
                            "action_type": proposal.proposed_action["type"],
                        }
                    )
            else:
                errors.append(
                    {
                        "action_id": proposal.action_id,
                        "error": "Action result did not pass canonical verification.",
                        "result": sanitize_payload(action_result),
                    }
                )
            if not verified:
                next_action = "Verification failed; do not retry without a new ARI decision."
            elif pending:
                next_action = pending[0].get("reason")
            else:
                next_action = "No pending action remains; ARI must decide final task disposition."
            checkpoint_id = self._insert_checkpoint(
                connection,
                proposal,
                trigger="action_verification_completed",
                event_type="action.verification_completed",
                state=self._checkpoint_state(
                    checkpoint,
                    completed_steps=completed,
                    pending_steps=pending,
                    artifacts=artifacts,
                    verification_results=[
                        *checkpoint["verification_results"],
                        {
                            "action_id": proposal.action_id,
                            "action_digest": proposal.action_digest,
                            **sanitize_payload(verification),
                        },
                    ],
                    errors=errors,
                    next_recommended_action=next_action,
                ),
                event_payload={
                    "action_id": proposal.action_id,
                    "verified": verified,
                    "verification": verification,
                    "remaining_pending_actions": len(pending),
                    "control_returned_to_ari": True,
                },
                idempotency_key=f"{proposal.idempotency_key}:verification",
                now=now,
            )
            self._set_execution(
                connection,
                execution_id,
                now=now,
                state=final_state,
                effect_status="verified" if verified else "effect_unverified",
                verification=verification,
                evidence=dict(verification["evidence"]),
                verification_checkpoint_id=checkpoint_id,
                finished_at=now,
            )
        return checkpoint_id

    def _persist_uncertain(
        self,
        proposal: RecoveredActionProposal,
        execution_id: str,
        *,
        error: dict[str, Any],
    ) -> str | None:
        """Record a post-dispatch failure as an uncertain effect, never as retryable."""
        now = self._now()
        with self.ledger._transaction() as connection:
            owned = self._owns_execution(connection, proposal, execution_id)
            if not owned and self._late_evidence_after_reconciliation(
                connection, proposal, execution_id, now=now, error=error
            ):
                return None
            self._set_execution(
                connection,
                execution_id,
                now=now,
                state=ActionIdempotencyState.EFFECT_UNCERTAIN,
                effect_status="uncertain",
                error=error,
                finished_at=now,
            )
            if not owned:
                return None
            checkpoint = self._latest_checkpoint_in(connection, proposal.task_id)
            return self._insert_checkpoint(
                connection,
                proposal,
                trigger="action_execution_uncertain",
                event_type="action.execution_uncertain",
                state=self._checkpoint_state(
                    checkpoint,
                    errors=[*checkpoint["errors"], {"action_id": proposal.action_id, **error}],
                    next_recommended_action=(
                        "Inspect side-effect evidence; do not retry this action blindly."
                    ),
                ),
                event_payload={"action_id": proposal.action_id, "result": None, "error": error},
                idempotency_key=f"{proposal.idempotency_key}:uncertain",
                now=now,
            )

    @staticmethod
    def _owns_execution(
        connection: sqlite3.Connection,
        proposal: RecoveredActionProposal,
        execution_id: str,
    ) -> bool:
        """Only the still-active attempt may advance canonical state for its execution."""
        execution = connection.execute(
            "select state from ari_execution_action_executions where execution_id = ?",
            (execution_id,),
        ).fetchone()
        task = ExecutionLedger._require_task(connection, proposal.task_id)
        return (
            execution is not None
            and execution["state"] == ActionIdempotencyState.EXECUTING
            and task["active_attempt_id"] == proposal.attempt_id
        )

    def _late_evidence_after_reconciliation(
        self,
        connection: sqlite3.Connection,
        proposal: RecoveredActionProposal,
        execution_id: str,
        *,
        now: datetime,
        result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> bool:
        """Keep a superseded attempt's late report from overwriting reconciled truth.

        The late report is recorded as an event. A late report on an effect confirmed
        absent contradicts that reconciliation, so the action returns to uncertain and
        blocks any retry until it is reconciled again.
        """
        row = connection.execute(
            "select state, error_json from ari_execution_action_executions where execution_id = ?",
            (execution_id,),
        ).fetchone()
        if row is None or row["state"] not in _RECONCILED_STATES:
            return False
        reopened = row["state"] == ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
        if reopened:
            self._set_execution(
                connection,
                execution_id,
                now=now,
                state=ActionIdempotencyState.EFFECT_UNCERTAIN,
                effect_status="late_report_contradicts_reconciliation",
                error={
                    "reason": "A superseded attempt reported on this action after its "
                    "effect was confirmed absent; the effect is uncertain again.",
                    "late_error": error,
                    "previous_error": (
                        None if row["error_json"] is None else json.loads(row["error_json"])
                    ),
                },
            )
        self._insert_event(
            connection,
            task_id=proposal.task_id,
            attempt_id=proposal.attempt_id,
            event_type="action.late_report_after_reconciliation",
            payload={
                "execution_id": execution_id,
                "action_id": proposal.action_id,
                "reconciled_state": row["state"],
                "reopened_as_uncertain": reopened,
                "result": result,
                "verification": verification,
                "error": error,
            },
            provenance={"authority": "ari", "operation": "late_report_after_reconciliation"},
            now=now,
        )
        return True

    def _insert_checkpoint(
        self,
        connection: sqlite3.Connection,
        proposal: RecoveredActionProposal,
        *,
        trigger: str,
        event_type: str,
        state: CheckpointState,
        event_payload: dict[str, Any],
        idempotency_key: str,
        now: datetime,
    ) -> str:
        checkpoint_id = f"checkpoint-{uuid4()}"
        ExecutionLedger._insert_boundary(
            connection,
            checkpoint_id=checkpoint_id,
            event_id=f"event-{uuid4()}",
            task_id=proposal.task_id,
            attempt_id=proposal.attempt_id,
            trigger=trigger,
            event_type=event_type,
            state_payload=sanitize_payload(asdict(state)),
            event_payload=sanitize_payload(event_payload),
            idempotency_key=idempotency_key,
            now=_iso(now),
        )
        return checkpoint_id

    @staticmethod
    def _checkpoint_in(connection: sqlite3.Connection, checkpoint_id: str) -> dict[str, Any]:
        row = connection.execute(
            "select * from ari_execution_checkpoints where checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Checkpoint {checkpoint_id} does not exist.")
        return _decode_row(row)

    def _latest_checkpoint_in(
        self,
        connection: sqlite3.Connection,
        task_id: str,
    ) -> dict[str, Any]:
        task = self._require_task(connection, task_id)
        if task["latest_checkpoint_id"] is None:
            raise ValueError("Task has no latest checkpoint.")
        return self._checkpoint_in(connection, str(task["latest_checkpoint_id"]))

    def _record_denial_checkpoint(
        self,
        proposal: RecoveredActionProposal,
        *,
        decision_id: str,
        decision: ResumeDecision,
        reason: str,
    ) -> str | None:
        task = self.ledger.get_task(proposal.task_id)
        if task is None or task.get("active_attempt_id") != proposal.attempt_id:
            return None
        checkpoint = self._latest_checkpoint(proposal.task_id)
        decisions = [*checkpoint["decisions"]]
        decisions.append(
            {
                "decision_id": decision_id,
                "decision": decision,
                "action_id": proposal.action_id,
                "reason": reason,
            }
        )
        stored = self.ledger.record_boundary(
            task_id=proposal.task_id,
            attempt_id=proposal.attempt_id,
            trigger="action_resume_denied",
            event_type="action.resume_stopped",
            state=self._checkpoint_state(
                checkpoint,
                decisions=decisions,
                next_recommended_action=reason,
            ),
            event_payload={
                "decision_id": decision_id,
                "decision": decision,
                "reason": reason,
                "action_id": proposal.action_id,
            },
        )
        return str(stored["checkpoint_id"])

    def _apply_denied_lifecycle(
        self,
        proposal: RecoveredActionProposal,
        decision: ResumeDecision,
        reason: str,
    ) -> None:
        if decision not in {ResumeDecision.REQUIRE_APPROVAL, ResumeDecision.BLOCKED}:
            return
        now = self._now()
        task_state = (
            TaskLifecycleState.AWAITING_APPROVAL
            if decision is ResumeDecision.REQUIRE_APPROVAL
            else TaskLifecycleState.BLOCKED
        )
        attempt_state = (
            AttemptLifecycleState.AWAITING_APPROVAL
            if decision is ResumeDecision.REQUIRE_APPROVAL
            else AttemptLifecycleState.BLOCKED
        )
        with self.ledger._transaction() as connection:
            task = self._require_task(connection, proposal.task_id)
            if task["active_attempt_id"] != proposal.attempt_id:
                return
            current_state = TaskLifecycleState(task["lifecycle_state"])
            if current_state in {
                TaskLifecycleState.PAUSED,
                TaskLifecycleState.CANCELLED,
                TaskLifecycleState.BLOCKED,
            }:
                return
            if reason.startswith("Global execution pause"):
                connection.execute(
                    """
                    update ari_execution_tasks
                    set recovery_block_reason = ?, updated_at = ?, row_version = row_version + 1
                    where task_id = ?
                    """,
                    (reason, _iso(now), proposal.task_id),
                )
                return
            connection.execute(
                """
                update ari_execution_tasks
                set lifecycle_state = ?, recovery_block_reason = ?, updated_at = ?,
                    row_version = row_version + 1
                where task_id = ?
                """,
                (task_state, reason, _iso(now), proposal.task_id),
            )
            connection.execute(
                """
                update ari_execution_attempts
                set lifecycle_state = ?, status = ?, waiting_reason = ?
                where attempt_id = ?
                """,
                (attempt_state, attempt_state, reason, proposal.attempt_id),
            )

    def _mark_executing(
        self,
        execution_id: str,
        proposal: RecoveredActionProposal,
        *,
        lock: LockIdentity,
        worker_identity: str,
        session_id: str,
        approval_reference: str | None,
    ) -> str:
        """Run the final authority checks and commit the crossing; return the fence id.

        The caller holds the logical action's dispatch lock, whose inode is recorded on
        the fence so a later landing proof can only succeed against that same lock.
        """
        now = self._now()
        pause_state = self.pause_state_reader()
        if bool(pause_state.get("paused")):
            raise ValueError(
                f"Global execution pause became active before dispatch: "
                f"{pause_state.get('reason') or 'no reason given'}."
            )
        with self.ledger._transaction() as connection:
            execution = connection.execute(
                "select * from ari_execution_action_executions where execution_id = ?",
                (execution_id,),
            ).fetchone()
            if execution is None or execution["state"] != (
                ActionIdempotencyState.AUTHORIZED_NOT_RUN
            ):
                raise ValueError("Action execution is not in authorized_not_run state.")
            if execution["idempotency_key"] != proposal.idempotency_key:
                raise ValueError("Dispatched action does not match the reserved action.")
            task = self._require_task(connection, proposal.task_id)
            attempt = connection.execute(
                "select * from ari_execution_attempts where attempt_id = ?",
                (proposal.attempt_id,),
            ).fetchone()
            if (
                task["active_attempt_id"] != proposal.attempt_id
                or task["lifecycle_state"] != TaskLifecycleState.EXECUTION_READY
                or task["latest_checkpoint_id"] != proposal.checkpoint_id
                or attempt is None
                or attempt["lifecycle_state"] != AttemptLifecycleState.EXECUTION_READY
            ):
                raise ValueError("Lifecycle changed before action dispatch.")
            if (
                attempt["worker_identity"] != worker_identity
                or attempt["session_id"] != session_id
            ):
                raise ValueError("Worker or session ownership changed before action dispatch.")
            if attempt["lease_expires_at"] is None or _parse(
                str(attempt["lease_expires_at"])
            ) <= now:
                raise ValueError("Worker lease became stale before action dispatch.")
            if attempt["continuation_acknowledgement_id"] is None:
                raise ValueError("Continuation acknowledgement disappeared before dispatch.")
            if proposal.approval_required:
                approval = connection.execute(
                    """
                    select * from ari_execution_action_approvals
                    where approval_id = ? and task_id = ? and action_digest = ?
                    """,
                    (
                        approval_reference,
                        proposal.task_id,
                        proposal.action_digest,
                    ),
                ).fetchone()
                if approval is None or approval["status"] != "approved":
                    raise ValueError("Action approval changed before dispatch.")
                if approval["expires_at"] is not None and _parse(
                    str(approval["expires_at"])
                ) <= now:
                    raise ValueError("Action approval expired before dispatch.")
            fence = DispatchFences.validate_crossing(
                connection,
                execution_id=execution_id,
                task_id=proposal.task_id,
                action_id=proposal.action_id,
                idempotency_key=proposal.idempotency_key,
                attempt_id=proposal.attempt_id,
            )
            DispatchFences.mark_crossing(
                connection, str(fence["fence_id"]), lock=lock, now=_iso(now)
            )
            connection.execute(
                """
                update ari_execution_action_executions
                set state = ?, effect_status = 'dispatch_started', started_at = ?, updated_at = ?
                where execution_id = ?
                """,
                (ActionIdempotencyState.EXECUTING, _iso(now), _iso(now), execution_id),
            )
        return str(fence["fence_id"])

    @staticmethod
    def _set_execution(
        connection: sqlite3.Connection,
        execution_id: str,
        *,
        now: datetime,
        state: ActionIdempotencyState | None = None,
        effect_status: str | None = None,
        pre_checkpoint_id: str | None = None,
        result_checkpoint_id: str | None = None,
        verification_checkpoint_id: str | None = None,
        result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        changes: dict[str, Any] = {"updated_at": _iso(now)}
        if state is not None:
            changes["state"] = state
        if effect_status is not None:
            changes["effect_status"] = effect_status
        if pre_checkpoint_id is not None:
            changes["pre_checkpoint_id"] = pre_checkpoint_id
        if result_checkpoint_id is not None:
            changes["result_checkpoint_id"] = result_checkpoint_id
        if verification_checkpoint_id is not None:
            changes["verification_checkpoint_id"] = verification_checkpoint_id
        if result is not None:
            changes["result_json"] = _json(sanitize_payload(result))
        if verification is not None:
            changes["verification_json"] = _json(sanitize_payload(verification))
        if evidence is not None:
            changes["evidence_json"] = _json(sanitize_payload(evidence))
        if error is not None:
            changes["error_json"] = _json(sanitize_payload(error))
        if finished_at is not None:
            changes["finished_at"] = _iso(finished_at)
        assignments = ", ".join(f"{column} = ?" for column in changes)
        connection.execute(
            f"update ari_execution_action_executions set {assignments} where execution_id = ?",
            (*changes.values(), execution_id),
        )

    def _deny_duplicate(
        self,
        proposal: RecoveredActionProposal,
        *,
        provenance: dict[str, Any] | None,
    ) -> RecoveredActionResumeResult:
        """Deny a non-fresh action and persist any state derived from attempt supersession."""
        state = proposal.idempotency_state
        governing = self._governing_execution(
            task_id=proposal.task_id,
            action_id=proposal.action_id,
            idempotency_key=proposal.idempotency_key,
            attempt_id=proposal.attempt_id,
        )
        reason = (
            self._duplicate_reason(state)
            if governing is None
            else self._governing_reason(proposal.action_id, governing[0], state)
        )
        decision_id = self._persist_decision(
            proposal,
            decision=ResumeDecision.DENY,
            reason=reason,
            approval_reference=proposal.approval_reference,
            provenance=provenance,
        )
        if governing is not None:
            execution, derived = governing
            stored = ActionIdempotencyState(execution["state"])
            if derived is not stored and derived in {
                ActionIdempotencyState.EFFECT_UNCERTAIN,
                ActionIdempotencyState.FAILED_BEFORE_EFFECT,
            }:
                now = self._now()
                with self.ledger._transaction() as connection:
                    connection.execute(
                        """
                        update ari_execution_action_executions
                        set state = ?, effect_status = ?, error_json = ?, finished_at = ?,
                            updated_at = ?
                        where execution_id = ? and state = ?
                        """,
                        (
                            derived,
                            "uncertain"
                            if derived is ActionIdempotencyState.EFFECT_UNCERTAIN
                            else "not_started",
                            _json({"reason": self._duplicate_reason(derived)}),
                            _iso(now),
                            _iso(now),
                            execution["execution_id"],
                            stored,
                        ),
                    )
                    if derived is ActionIdempotencyState.FAILED_BEFORE_EFFECT:
                        DispatchFences.revoke_unused(
                            connection,
                            str(execution["execution_id"]),
                            now=_iso(now),
                            reason=self._duplicate_reason(derived),
                        )
        return self._result(
            proposal,
            decision_id=decision_id,
            decision=ResumeDecision.DENY,
            reason=reason,
            executed=False,
            idempotency_state=state,
            approval_reference=proposal.approval_reference,
        )

    def _stop_before_effect(
        self,
        proposal: RecoveredActionProposal,
        execution_id: str,
        *,
        decision: ResumeDecision,
        reason: str,
        approval_reference: str | None,
        provenance: dict[str, Any] | None,
        pre_checkpoint_id: str,
    ) -> RecoveredActionResumeResult:
        """Release a reservation that provably never dispatched."""
        decision_id = f"resume-decision-{uuid4()}"
        now = self._now()
        with self.ledger._transaction() as connection:
            self._insert_decision(
                connection,
                proposal,
                decision_id=decision_id,
                decision=decision,
                reason=reason,
                approval_reference=approval_reference,
                provenance=provenance,
                now=now,
            )
            self._set_execution(
                connection,
                execution_id,
                now=now,
                state=ActionIdempotencyState.FAILED_BEFORE_EFFECT,
                effect_status="not_started",
                error={"reason": reason},
                finished_at=now,
            )
            DispatchFences.revoke_unused(connection, execution_id, now=_iso(now), reason=reason)
        self._apply_denied_lifecycle(proposal, decision, reason)
        denial_checkpoint = self._record_denial_checkpoint(
            proposal,
            decision_id=decision_id,
            decision=decision,
            reason=reason,
        )
        return self._result(
            proposal,
            decision_id=decision_id,
            decision=decision,
            reason=reason,
            executed=False,
            idempotency_state=ActionIdempotencyState.FAILED_BEFORE_EFFECT,
            approval_reference=approval_reference,
            pre_checkpoint_id=pre_checkpoint_id,
            result_checkpoint_id=denial_checkpoint,
        )

    def _superseded_result(
        self,
        proposal: RecoveredActionProposal,
        *,
        decision_id: str,
        approval_reference: str | None,
        pre_checkpoint_id: str,
        action_result: dict[str, Any],
        verification: dict[str, Any] | None = None,
    ) -> RecoveredActionResumeResult:
        return self._result(
            proposal,
            decision_id=decision_id,
            decision=ResumeDecision.ALLOW,
            reason=_SUPERSEDED_REASON,
            executed=True,
            idempotency_state=ActionIdempotencyState.EFFECT_UNCERTAIN,
            approval_reference=approval_reference,
            pre_checkpoint_id=pre_checkpoint_id,
            result=action_result,
            verification=verification,
        )

    def _find_approval(
        self,
        *,
        task_id: str,
        action_digest: str,
        target_resources: tuple[str, ...],
        authority_snapshot_hash: str | None,
        include_expired: bool,
    ) -> dict[str, Any] | None:
        approvals = self.ledger._many(
            """
            select * from ari_execution_action_approvals
            where task_id = ? and action_digest = ? and authority_snapshot_hash is ?
            order by rowid desc
            """,
            (task_id, action_digest, authority_snapshot_hash),
        )
        for approval in approvals:
            if tuple(approval["target_resources"]) != target_resources:
                continue
            if not include_expired and approval["expires_at"] is not None and (
                _parse(str(approval["expires_at"])) <= self._now()
            ):
                continue
            return approval
        return None

    def _governing_execution(
        self,
        *,
        task_id: str,
        action_id: str,
        idempotency_key: str,
        attempt_id: str,
    ) -> tuple[dict[str, Any], ActionIdempotencyState] | None:
        rows = self.ledger._many(_TASK_EXECUTIONS, (task_id,))
        return self._select_governing(
            rows, action_id=action_id, idempotency_key=idempotency_key, attempt_id=attempt_id
        )

    @classmethod
    def _select_governing(
        cls,
        rows: list[dict[str, Any]],
        *,
        action_id: str,
        idempotency_key: str,
        attempt_id: str,
    ) -> tuple[dict[str, Any], ActionIdempotencyState] | None:
        """Pick the execution record that decides whether this action may dispatch.

        `rows` are every execution of the task, newest first. For the same action_id the
        exact idempotency key always governs; otherwise any earlier execution governs
        unless it provably stopped before effect or is safe to redispatch. A revised
        digest therefore cannot re-run an action whose effect is uncertain, unverified,
        confirmed, or absent without proof that it can no longer land.

        Any other action of the task that is still unresolved governs too: ARI cannot
        tell whether a renamed action repeats its effect.
        """
        same = [row for row in rows if row["action_id"] == action_id]
        for row in same:
            if row["idempotency_key"] == idempotency_key:
                return row, cls._effective_state(row, attempt_id)
        for row in same:
            state = cls._effective_state(row, attempt_id)
            if state is ActionIdempotencyState.FAILED_BEFORE_EFFECT:
                continue
            if cls._safe_to_redispatch(row, state):
                continue
            return row, state
        for row in rows:
            if row["action_id"] == action_id:
                continue
            state = cls._effective_state(row, attempt_id)
            if state in _UNRESOLVED_STATES or (
                state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
                and not cls._safe_to_redispatch(row, state)
            ):
                return row, state
        return None

    @staticmethod
    def _safe_to_redispatch(row: dict[str, Any], state: ActionIdempotencyState) -> bool:
        """SAFE TO REDISPATCH: absence observed after landing was ruled out.

        Both facts must come from one chain: the fence's landing token (issued only
        once ARI established the dispatch can no longer produce its effect) and an
        absence reconciliation that presented that same token. An absence recorded
        before landing was ruled out never qualifies, whatever happens to the fence
        afterwards.
        """
        fence_token = row.get("fence_landing_token")
        return (
            state is ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT
            and bool(row.get("reconciliation_redispatch_safe"))
            and fence_token is not None
            and row.get("reconciliation_landing_token") == fence_token
        )

    @staticmethod
    def _effective_state(row: dict[str, Any], attempt_id: str) -> ActionIdempotencyState:
        """Derive the durable state once the reserving attempt has been superseded."""
        state = ActionIdempotencyState(row["state"])
        if row["attempt_id"] == attempt_id:
            return state
        if state is ActionIdempotencyState.EXECUTING:
            return ActionIdempotencyState.EFFECT_UNCERTAIN
        if state is ActionIdempotencyState.AUTHORIZED_NOT_RUN:
            # Dispatch commits `executing` before the tool runs, so a reservation left
            # by another attempt never reached the side effect.
            return ActionIdempotencyState.FAILED_BEFORE_EFFECT
        return state

    def _latest_action_execution(self, task_id: str) -> dict[str, Any] | None:
        return self.ledger._one(
            """
            select * from ari_execution_action_executions
            where task_id = ? order by rowid desc limit 1
            """,
            (task_id,),
        )

    @staticmethod
    def _idempotency_state(
        governing: tuple[dict[str, Any], ActionIdempotencyState] | None,
        checkpoint: dict[str, Any],
    ) -> ActionIdempotencyState:
        if governing is None:
            return ActionIdempotencyState.NEVER_ATTEMPTED
        execution, state = governing
        if state.value != execution["state"]:
            return state
        completed_ids = {str(item.get("action_id")) for item in checkpoint["completed_steps"]}
        if execution["action_id"] in completed_ids:
            return ActionIdempotencyState.ALREADY_COMPLETED
        return state

    @staticmethod
    def _target_resources(action: dict[str, Any]) -> tuple[str, ...]:
        action_type = str(action.get("type") or "")
        if action_type in {"read_file", "write_file", "patch_file"}:
            return (str(action.get("path") or ""),)
        if action_type == "run_command":
            return ("command:" + " ".join(action.get("command") or []),)
        return (f"action:{action_type}",)

    @staticmethod
    def _action_digest(
        action: dict[str, Any],
        target_resources: tuple[str, ...],
        authority_snapshot_hash: str | None,
    ) -> str:
        payload = {
            "action": action,
            "target_resources": target_resources,
            "authority_snapshot_hash": authority_snapshot_hash,
        }
        return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _idempotency_key(task_id: str, action_id: str, action_digest: str) -> str:
        material = f"{task_id}:{action_id}:{action_digest}"
        return "recovered-action:" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _proposal_from_decision(
        self,
        decision: dict[str, Any],
        state: ActionIdempotencyState,
        *,
        attempt_id: str,
    ) -> RecoveredActionProposal:
        approval = decision.get("approval_reference")
        return RecoveredActionProposal(
            task_id=str(decision["task_id"]),
            attempt_id=attempt_id,
            checkpoint_id=str(decision["checkpoint_id"]),
            action_id=str(decision["action_id"]),
            proposed_action=dict(decision["proposed_action"]),
            action_digest=str(decision["action_digest"]),
            target_resources=tuple(decision["target_resources"]),
            authority_snapshot_ref=decision.get("authority_snapshot_ref"),
            authority_snapshot_hash=decision.get("authority_snapshot_hash"),
            authority_scope=dict(decision["authority_scope"]),
            approval_required=approval is not None,
            approval_reference=approval,
            restrictions=tuple(decision["restrictions"]),
            idempotency_key=str(decision["idempotency_key"]),
            idempotency_state=state,
            provenance=dict(decision["provenance"]),
        )

    def _latest_checkpoint(self, task_id: str) -> dict[str, Any]:
        task = self.ledger.get_task(task_id)
        if task is None or task["latest_checkpoint_id"] is None:
            raise ValueError("Task has no latest checkpoint.")
        checkpoint = self.ledger.get_checkpoint(str(task["latest_checkpoint_id"]))
        assert checkpoint is not None
        return checkpoint

    @staticmethod
    def _checkpoint_state(checkpoint: dict[str, Any], **changes: Any) -> CheckpointState:
        values: dict[str, Any] = {
            "objective": checkpoint["objective"],
            "success_criteria": tuple(checkpoint["success_criteria"]),
            "current_plan": dict(checkpoint["current_plan"]),
            "completed_steps": tuple(checkpoint["completed_steps"]),
            "pending_steps": tuple(checkpoint["pending_steps"]),
            "important_findings": tuple(checkpoint["important_findings"]),
            "assumptions": tuple(checkpoint["assumptions"]),
            "decisions": tuple(checkpoint["decisions"]),
            "artifacts": tuple(checkpoint["artifacts"]),
            "actions_taken": tuple(checkpoint["actions_taken"]),
            "verification_results": tuple(checkpoint["verification_results"]),
            "errors": tuple(checkpoint["errors"]),
            "provider": dict(checkpoint["provider"]),
            "capacity_observations": tuple(checkpoint["capacity_observations"]),
            "next_recommended_action": checkpoint["next_recommended_action"],
            "provenance": dict(checkpoint["provenance"]),
            "restrictions": tuple(checkpoint["restrictions"]),
            "authority_scope": dict(checkpoint["authority_scope"]),
            "approval_state": dict(checkpoint["approval_state"]),
        }
        values.update(changes)
        for key in (
            "completed_steps",
            "pending_steps",
            "important_findings",
            "assumptions",
            "decisions",
            "artifacts",
            "actions_taken",
            "verification_results",
            "errors",
            "capacity_observations",
            "restrictions",
        ):
            values[key] = tuple(values[key])
        return CheckpointState(**values)

    @classmethod
    def _governing_reason(
        cls,
        action_id: str,
        execution: dict[str, Any],
        state: ActionIdempotencyState,
    ) -> str:
        if execution["action_id"] == action_id:
            return cls._duplicate_reason(state)
        return (
            f"Action {execution['action_id']} in this task is unresolved ({state}); no "
            "action in the task may dispatch until it is resolved, because a different "
            "action could repeat its effect."
        )

    @staticmethod
    def _duplicate_reason(state: ActionIdempotencyState) -> str:
        reasons = {
            ActionIdempotencyState.AUTHORIZED_NOT_RUN: (
                "The action is already authorized and reserved; duplicate dispatch is denied."
            ),
            ActionIdempotencyState.EXECUTING: (
                "The action is currently executing; duplicate dispatch is denied."
            ),
            ActionIdempotencyState.SUCCEEDED: (
                "The action already succeeded; duplicate dispatch is denied."
            ),
            ActionIdempotencyState.FAILED_BEFORE_EFFECT: (
                "The prior action stopped safely before effect; a new explicit retry design is required."
            ),
            ActionIdempotencyState.EFFECT_UNCERTAIN: (
                "The action effect may have occurred; blind retry is denied."
            ),
            ActionIdempotencyState.VERIFICATION_FAILED: (
                "The action ran without successful verification; blind retry is denied."
            ),
            ActionIdempotencyState.ALREADY_COMPLETED: (
                "The canonical checkpoint already marks this action complete."
            ),
            ActionIdempotencyState.NEVER_ATTEMPTED: "The action has never been attempted.",
            ActionIdempotencyState.EFFECT_CONFIRMED: (
                "Reconciliation confirmed the action's effect occurred; it is never re-dispatched."
            ),
            ActionIdempotencyState.EFFECT_CONFIRMED_ABSENT: (
                "Reconciliation recorded the effect as absent, but a retry is safe only "
                "when that absence was observed after ARI ruled out the earlier dispatch "
                "landing (a matching landing token), plus an explicit canonical plan "
                "revision and a new ARI decision."
            ),
        }
        return reasons[state]

    @staticmethod
    def _result(
        proposal: RecoveredActionProposal,
        *,
        decision_id: str,
        decision: ResumeDecision,
        reason: str,
        executed: bool,
        idempotency_state: ActionIdempotencyState,
        approval_reference: str | None = None,
        pre_checkpoint_id: str | None = None,
        result_checkpoint_id: str | None = None,
        verification_checkpoint_id: str | None = None,
        result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> RecoveredActionResumeResult:
        return RecoveredActionResumeResult(
            task_id=proposal.task_id,
            attempt_id=proposal.attempt_id,
            decision_id=decision_id,
            decision=decision,
            reason=reason,
            proposal=proposal,
            executed=executed,
            idempotency_state=idempotency_state,
            approval_reference=approval_reference,
            pre_checkpoint_id=pre_checkpoint_id,
            result_checkpoint_id=result_checkpoint_id,
            verification_checkpoint_id=verification_checkpoint_id,
            result=result,
            verification=verification,
        )

    @staticmethod
    def _require_task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        return ExecutionLedger._require_task(connection, task_id)

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

    def _now(self) -> datetime:
        return self._normalize_time(self.clock())

    @staticmethod
    def _normalize_time(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Gateway clock and approval expiry must be timezone-aware.")
        return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
