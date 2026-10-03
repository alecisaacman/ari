# Recovered Action Authority Gateway

`RecoveredActionGateway` is the canonical ARI-owned boundary for executing one
pending action after worker-session recovery. A replacement worker can describe
and acknowledge continuation state, but it cannot authorize itself.

## One-action flow

1. ARI derives the first pending action from the latest canonical checkpoint.
2. ARI calculates the action digest, target resources, and durable idempotency key.
3. ARI revalidates global and task pause state, cancellation, blocking, lifecycle,
   active attempt, lease, worker/session identity, continuation acknowledgement,
   authority snapshot, restrictions, action-bound approval, tool allowlist, and
   execution-root scope.
4. ARI persists an `allow`, `deny`, `require_approval`, or `blocked` resume decision.
5. On allow, one immediate transaction re-checks that the evaluated checkpoint and
   active attempt are still current, then commits the allow decision, the
   idempotency reservation, and the pre-action checkpoint together.
6. ARI re-derives the pending action and refuses dispatch unless it is exactly the
   reserved action. It takes the logical action's dispatch lock, then repeats the
   volatile checks, validates the dispatch fence, and commits `executing` with
   the fence crossing and the held lock's inode. Then it calls the existing
   `execute_action` plus `ExecutionRoot` boundary, and records the dispatch as
   returned before releasing the lock. A return rules out a late effect only for
   `in_process` effects. See [Dispatch Safety Boundary](dispatch-safety.md).
7. ARI commits the raw action result with its checkpoint, verifies independently,
   then commits the verification checkpoint, the pending-to-completed move, and
   the final execution state in one transaction.
8. Control returns to ARI. A following pending action requires another explicit
   resume call and another durable decision.

The API surface exposes read-only proposal/inspection plus explicit approval and
one-action resume calls:

- `GET /execution/tasks/{task_id}/next-recovered-action`
- `POST /execution/tasks/{task_id}/next-recovered-action/approve`
- `POST /execution/tasks/{task_id}/resume-one`

The server-configured `ARI_EXECUTION_ROOT`, not a request parameter, selects the
execution root for API calls. Requested roots elsewhere may only narrow it; see
[Execution Authority](execution-authority.md).

## Approval continuity

Approvals bind to the task, normalized action digest, target resources, and
authority snapshot. They are not bound to a provider and do not widen during
worker replacement. A changed action, target, authority snapshot, missing
approval, or expired approval prevents execution. Awaiting approval is a durable
lifecycle gate, not a worker failure.

## Idempotency and uncertainty

The idempotency key is derived from `task_id`, canonical `action_id`, and the
action digest. Its durable states are:

- `never_attempted`
- `authorized_not_run`
- `executing`
- `succeeded`
- `failed_before_effect`
- `effect_may_have_occurred`
- `verification_failed`
- `already_completed` (derived from the canonical checkpoint)
- `effect_confirmed` and `effect_confirmed_absent` (set only by
  [uncertain-effect reconciliation](effect-reconciliation.md))

Dispatch is reserved before the tool runs. A duplicate or concurrent request
cannot reserve the same key; it receives a durable `deny` decision. Exceptions
after dispatch are recorded as uncertain and are never blindly retried.

Idempotency is governed per canonical `action_id`, not only per digest. The exact
key always governs. Otherwise any earlier execution of the same `action_id`
governs unless it stopped before effect or is
[safe to redispatch](dispatch-safety.md#safe-to-redispatch): its effect was
confirmed absent by an observation bound to proof that the dispatch can no longer
land. A revised plan digest therefore cannot re-run an action whose effect is
executing, uncertain, unverified, confirmed, succeeded, or absent without that
proof. Those actions can run only under a new digest, meaning an explicit
canonical plan revision.

Governance is also task-wide. While any action of the task is unresolved, no
other action of the task may dispatch, so renaming an action cannot repeat its
effect. `inspect_task` reports `redispatch_safety` for every execution.

A superseded attempt that reports after its execution was reconciled cannot
overwrite that truth. The report is recorded as an event, and a confirmed-absent
effect returns to uncertain.

When the reserving attempt has been superseded, ARI derives and persists its
state for the replacement worker:

- `executing` becomes `effect_may_have_occurred`
- `authorized_not_run` becomes `failed_before_effect`, because dispatch commits
  `executing` before the tool runs

An attempt superseded while its action runs cannot advance canonical checkpoints.
Its result is kept on the execution record as evidence, and the effect is marked
uncertain.

## Remaining bypass paths

This slice intentionally converges only recovered pending actions. The following
legacy paths still invoke execution machinery without this recovered-action
gateway and require a later convergence slice:

- `ExecutionController.run()` multi-action plans
- operator actions in `modules/execution/engine.py`
- coding-loop execution and approved retry execution
- direct execution API file and command endpoints

They remain bounded by their existing policy, approval, and sandbox checks, but
they do not yet share this decision/idempotency/checkpoint sequence.

## Known limits

- The global pause marker is filesystem-backed while task pause is ledger-backed;
  both are checked immediately before dispatch but are not one database transaction.
- API caller authentication and proof that `approvedBy` represents Alec remain an
  outer service/authentication concern.
- Uncertain and unverified effects are resolved only by explicit
  [reconciliation](effect-reconciliation.md); the gateway never infers or retries them.
- `failed_before_effect` for an unchanged digest stays denied. Re-running it
  requires a canonical plan revision or a future explicit retry design.
- A crash after `executing` commits always resolves to uncertainty, even when the
  result was already recorded, until it is reconciled.
- The gateway uses the current backend only. Provider routing and failover are not
  part of this slice.
