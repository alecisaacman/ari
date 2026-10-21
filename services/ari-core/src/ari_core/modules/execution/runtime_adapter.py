"""The one canonical path for runtime-loop side effects.

Every effectful step a runtime loop takes (a provider worker invocation, a
verification command, a legacy controller action) becomes its own ARI execution
task with exactly one planned action. ARI plans it, hands it to a named worker,
and dispatches it once through `RecoveredActionGateway.resume_one`, so it gets the
same pause checks, authority scope, approval binding, idempotency reservation,
dispatch fence, verification, and checkpoints as a recovered action. Control then
returns to the calling loop, which decides the next step. A retry is a newly
planned step, never a redispatch of an earlier one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ...core.paths import DB_PATH
from .contracts import (
    ActionIdempotencyState,
    CheckpointState,
    ContinuationAcknowledgement,
    ExecutionResultContract,
    ExecutionTaskSpec,
    ResumeDecision,
)
from .dispatch import classify_effect_terminality
from .executor import execute_action
from .gateway import RecoveredActionGateway
from .ledger import ExecutionLedger
from .sandbox import ExecutionRoot
from .session import ExecutionSessionManager
from .tools import (
    DEFAULT_EXECUTION_TOOL_REGISTRY,
    ExecutionTool,
    ExecutionToolRegistry,
)

WORKER_INVOCATION_ACTION = "invoke_worker"
RUNTIME_AUTHORITY_SNAPSHOT_REF = "runtime-adapter-v1"
DEFAULT_WORKER_TIMEOUT_SECONDS = 600
MAX_WORKER_TIMEOUT_SECONDS = 3600
DEFAULT_LEASE_SECONDS = MAX_WORKER_TIMEOUT_SECONDS + 300

Clock = Callable[[], datetime]
PauseStateReader = Callable[[], dict[str, Any]]


class WorkerInvoker(Protocol):
    """A provider worker ARI can hand a prompt to. ARI never treats it as an authority."""

    def invoke(
        self,
        prompt: str,
        *,
        cwd: Path | str | None = None,
        timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class CanonicalStepResult:
    """What ARI decided and observed for one canonical runtime step."""

    task_id: str
    action_id: str
    action_type: str
    worker_identity: str
    decision: ResumeDecision
    reason: str
    executed: bool
    idempotency_state: ActionIdempotencyState
    result: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None

    @property
    def succeeded(self) -> bool:
        return self.executed and self.idempotency_state is ActionIdempotencyState.SUCCEEDED

    @property
    def effect_uncertain(self) -> bool:
        return self.idempotency_state is ActionIdempotencyState.EFFECT_UNCERTAIN

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = str(self.decision)
        payload["idempotency_state"] = str(self.idempotency_state)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeStepRequest:
    action: dict[str, Any]
    objective: str
    reason: str
    worker_identity: str
    loop_id: str | None = None
    restrictions: tuple[str, ...] = ()
    approval_required: bool = False
    worker_capabilities: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreparedRuntimeStep:
    """A planned step handed to its worker and ready for one gateway decision."""

    task_id: str
    action_id: str
    action_type: str
    attempt_id: str
    session_id: str
    worker_identity: str
    objective: str
    loop_id: str | None


class RuntimeToolRegistry(ExecutionToolRegistry):
    """The default tools plus `invoke_worker` for the workers this adapter was given.

    `invoke_worker` is deliberately not in the default registry, so planners never see
    it and cannot propose a worker invocation. Only runtime loops that hold a
    configured worker can dispatch one.
    """

    def __init__(self, worker_identities: Sequence[str]) -> None:
        super().__init__(
            (
                *_default_tools(),
                ExecutionTool(
                    name="Invoke worker",
                    action_type=WORKER_INVOCATION_ACTION,
                    description=(
                        "Hand one prompt to a configured provider worker in the execution "
                        "root. Operator-configured arbitrary code; never safe to redispatch."
                    ),
                    mutates_files=True,
                    required_payload_keys=("worker", "prompt"),
                ),
            )
        )
        self._worker_identities = frozenset(worker_identities)

    def validate_execution_action(
        self,
        action: dict[str, Any],
        *,
        execution_root: ExecutionRoot,
        allowed_files: set[str] | None = None,
    ) -> str | None:
        error = super().validate_execution_action(
            action, execution_root=execution_root, allowed_files=allowed_files
        )
        if error is not None or str(action.get("type") or "") != WORKER_INVOCATION_ACTION:
            return error
        if str(action.get("worker") or "") not in self._worker_identities:
            return f"Worker {action.get('worker')!r} is not configured for this runtime adapter."
        prompt = action.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return "invoke_worker actions require a non-empty prompt."
        timeout = action.get("timeout_seconds", DEFAULT_WORKER_TIMEOUT_SECONDS)
        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or not 1 <= timeout <= MAX_WORKER_TIMEOUT_SECONDS
        ):
            return (
                f"invoke_worker timeout_seconds must be between 1 and {MAX_WORKER_TIMEOUT_SECONDS}."
            )
        return None


class RuntimeExecutionAdapter:
    """Route one runtime step at a time through ARI's canonical execution authority."""

    def __init__(
        self,
        db_path: Path = DB_PATH,
        *,
        execution_root: Path | str | None = None,
        workers: Mapping[str, WorkerInvoker] | None = None,
        clock: Clock | None = None,
        pause_state_reader: PauseStateReader | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self.db_path = db_path
        # Resolved now: an unconfigured or live-runtime root fails closed before any
        # task is created.
        self.execution_root = ExecutionRoot(execution_root)
        self.workers = dict(workers or {})
        self.lease_seconds = lease_seconds
        self.ledger = ExecutionLedger(db_path)
        self.sessions = ExecutionSessionManager(db_path, clock=clock)
        self.gateway = RecoveredActionGateway(
            db_path,
            execution_root=self.execution_root.root,
            clock=clock,
            pause_state_reader=pause_state_reader,
            tool_registry=RuntimeToolRegistry(tuple(self.workers)),
            action_executor=self._dispatch,
            effect_terminality=classify_effect_terminality,
        )

    def run_step(self, request: RuntimeStepRequest) -> CanonicalStepResult:
        """Plan, hand off, and dispatch at most one action; then return control."""
        return self.dispatch_step(self.prepare_step(request))

    def prepare_step(self, request: RuntimeStepRequest) -> PreparedRuntimeStep:
        """Persist the one-action task, hand it to the worker, and record its acknowledgement."""
        action = dict(request.action)
        action_type = str(action.get("type") or "")
        if not action_type:
            raise ValueError("A runtime step requires an action type.")
        if not request.worker_identity.strip():
            raise ValueError("A runtime step requires a worker identity.")
        restrictions = tuple(dict.fromkeys(request.restrictions))
        if action_type == WORKER_INVOCATION_ACTION and "no network" in {
            item.strip().lower() for item in restrictions
        }:
            raise ValueError("A provider worker cannot run under a 'no network' restriction.")

        task_id = f"runtime-step-{uuid4()}"
        action_id = f"action-{uuid4()}"
        authority_scope = _authority_scope(action)
        approval_state = {
            "required": request.approval_required,
            "status": "pending" if request.approval_required else "not_required",
        }
        snapshot_hash = _snapshot_hash(authority_scope, restrictions, approval_state)
        provenance = {
            **request.provenance,
            "source": "runtime_adapter",
            "loop_id": request.loop_id,
            "worker_identity": request.worker_identity,
            "worker_capabilities": list(request.worker_capabilities),
        }
        _, planning_attempt_id = self.ledger.create_task(
            ExecutionTaskSpec(
                task_id=task_id,
                objective=request.objective,
                success_criteria=(f"The {action_type} step is executed and verified by ARI.",),
                linked_task_id=request.loop_id,
                authority_snapshot_ref=RUNTIME_AUTHORITY_SNAPSHOT_REF,
                authority_snapshot_hash=snapshot_hash,
                restrictions=restrictions,
                authority_scope=authority_scope,
                approval_state=approval_state,
            ),
            executor_id="ari-runtime",
            backend_id=request.worker_identity,
            provenance=provenance,
        )
        planned = {
            "id": action_id,
            "action_type": action_type,
            "payload": {key: value for key, value in action.items() if key != "type"},
            "execution_action": action,
            "reason": request.reason,
            "requires_approval": request.approval_required,
        }
        self.ledger.record_boundary(
            task_id=task_id,
            attempt_id=planning_attempt_id,
            trigger="plan_created",
            event_type="plan.created",
            state=CheckpointState(
                objective=request.objective,
                success_criteria=(f"The {action_type} step is executed and verified by ARI.",),
                current_plan={"id": f"plan-{uuid4()}", "actions": [planned]},
                pending_steps=(
                    {
                        "action_id": action_id,
                        "action_type": action_type,
                        "reason": request.reason,
                    },
                ),
                provider={"executor_id": "ari-runtime", "backend_id": request.worker_identity},
                next_recommended_action=request.reason,
                provenance=provenance,
                restrictions=restrictions,
                authority_scope=authority_scope,
                approval_state=approval_state,
            ),
            event_payload={"action_id": action_id, "action_type": action_type},
            idempotency_key=f"runtime-step-planned:{task_id}",
        )
        handoff = self.sessions.hand_off_to_worker(
            planning_attempt_id,
            worker_identity=request.worker_identity,
            lease_seconds=self.lease_seconds,
        )
        assert handoff.replacement_attempt_id is not None
        assert handoff.continuation_packet_id is not None
        self._acknowledge(handoff.continuation_packet_id, request.worker_identity)
        attempt = self.ledger._one(
            "select session_id from ari_execution_attempts where attempt_id = ?",
            (handoff.replacement_attempt_id,),
        )
        assert attempt is not None
        return PreparedRuntimeStep(
            task_id=task_id,
            action_id=action_id,
            action_type=action_type,
            attempt_id=handoff.replacement_attempt_id,
            session_id=str(attempt["session_id"]),
            worker_identity=request.worker_identity,
            objective=request.objective,
            loop_id=request.loop_id,
        )

    def dispatch_step(self, prepared: PreparedRuntimeStep) -> CanonicalStepResult:
        """Ask the gateway for exactly one decision on the prepared step."""
        resumed = self.gateway.resume_one(
            task_id=prepared.task_id,
            attempt_id=prepared.attempt_id,
            worker_identity=prepared.worker_identity,
            session_id=prepared.session_id,
            provenance={"authority": "ari", "operation": "runtime_step", "loop_id": prepared.loop_id},
        )
        step = CanonicalStepResult(
            task_id=prepared.task_id,
            action_id=prepared.action_id,
            action_type=prepared.action_type,
            worker_identity=prepared.worker_identity,
            decision=resumed.decision,
            reason=resumed.reason,
            executed=resumed.executed,
            idempotency_state=resumed.idempotency_state,
            result=resumed.result,
            verification=resumed.verification,
        )
        if step.succeeded:
            self._close_succeeded(step, prepared.attempt_id, prepared.objective)
        return step

    def _acknowledge(self, packet_id: str, worker_identity: str) -> None:
        # Subprocess workers cannot speak the continuation protocol, so the adapter
        # acknowledges on their behalf. The acknowledgement is copied from ARI's own
        # packet, so it can only confirm canonical state, never widen it.
        stored = self.ledger._one(
            "select * from ari_execution_continuation_packets where packet_id = ?",
            (packet_id,),
        )
        assert stored is not None
        packet = stored["packet"]
        self.sessions.acknowledge_continuation(
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

    def _close_succeeded(self, step: CanonicalStepResult, attempt_id: str, objective: str) -> None:
        task = self.ledger.get_task(step.task_id)
        if task is None or task["latest_checkpoint_id"] is None:
            return
        self.ledger.record_result(
            task_id=step.task_id,
            attempt_id=attempt_id,
            result=ExecutionResultContract(
                task_id=step.task_id,
                status="completed",
                objective=objective,
                outcome=step.reason,
                success_criteria_evaluation=(
                    {"criterion": "executed and verified", "met": True},
                ),
                verification=({"action_id": step.action_id, **(step.verification or {})},),
                provider_provenance=({"worker_identity": step.worker_identity},),
            ),
            final_checkpoint_id=str(task["latest_checkpoint_id"]),
        )

    def _dispatch(self, action: dict[str, Any], execution_root: Path | str | None) -> dict[str, Any]:
        if str(action.get("type") or "") != WORKER_INVOCATION_ACTION:
            return execute_action(action, execution_root)
        worker = self.workers[str(action["worker"])]
        invocation = worker.invoke(
            str(action["prompt"]),
            cwd=self.execution_root.root,
            timeout_seconds=int(action.get("timeout_seconds", DEFAULT_WORKER_TIMEOUT_SECONDS)),
        )
        payload = invocation.to_dict() if hasattr(invocation, "to_dict") else dict(invocation)
        return {**payload, "success": bool(payload.get("success"))}


def _default_tools() -> tuple[ExecutionTool, ...]:
    return tuple(
        ExecutionTool(**tool)  # type: ignore[arg-type]
        for tool in DEFAULT_EXECUTION_TOOL_REGISTRY.list_tools()
    )


def _authority_scope(action: dict[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {"permitted_side_effects": [str(action["type"])]}
    path = action.get("path")
    if isinstance(path, str) and path:
        scope["filesystem"] = [path]
    return scope


def _snapshot_hash(
    authority_scope: dict[str, Any],
    restrictions: tuple[str, ...],
    approval_state: dict[str, Any],
) -> str:
    material = json.dumps(
        {
            "ref": RUNTIME_AUTHORITY_SNAPSHOT_REF,
            "authority_scope": authority_scope,
            "restrictions": list(restrictions),
            "approval_state": approval_state,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
