# Runtime Execution Convergence

ARI's runtime loops plan; ARI's execution authority acts. Every effectful step a
runtime loop takes goes through one path:
`modules/execution/runtime_adapter.py` → `RecoveredActionGateway.resume_one`.

## Who uses the path

| Caller | Step it dispatches | Worker identity |
| --- | --- | --- |
| `runtime/loop_runner.py` (`LoopRunner`, `run_goal_loop`) | `invoke_worker` per cycle | `runtime-worker:<backend>` |
| `runtime/self_improvement_runner.py` | its worker loop (above) and each verification command | as above, `ari-verifier` |
| `runtime/verification_profiles.py` (`TestPasses`, `command_succeeds`) | `run_command` | `ari-verifier` |
| `runtime/repo_inspector.py` (`verification_commands`) | `run_command` | `ari-verifier` |
| legacy `ari_core/executor.py` (`execute_intent`, used by `controller.py`, orchestration, and approvals) | `read_file`, `run_command` | `ari-legacy-controller` |

`runtime/worker_backend.py` still starts the provider process, but only as the
adapter's executor for an `invoke_worker` action the gateway has already
authorized. No runtime loop calls a worker directly.

## One step

`RuntimeExecutionAdapter.run_step` is `prepare_step` followed by `dispatch_step`:

1. **Plan.** ARI creates an execution task with exactly one planned action. The
   authority scope permits only that action type (and only that path, for file
   actions). Restrictions and approval requirements come from the caller. The task
   is linked to the loop through `linked_task_id`.
2. **Hand off.** `ExecutionSessionManager.hand_off_to_worker` closes ARI's planning
   attempt and gives the named worker a leased attempt and a continuation packet.
3. **Acknowledge.** Subprocess workers cannot speak the continuation protocol, so
   the adapter acknowledges for them, copying ARI's own packet. The acknowledgement
   can confirm canonical state but cannot change it.
4. **Decide and dispatch once.** `resume_one` runs every gateway check (global and
   task pause, lifecycle, lease, identity, approval binding, tool validation,
   restrictions, scope), reserves the idempotency key, crosses a dispatch fence,
   runs the action, verifies it, and records checkpoints.
5. **Return control.** The loop reads the result and decides its next step. A
   succeeded task is closed with a canonical result.

A loop may plan many steps, but each one is a new task and a new decision. A retry
is a newly planned step, never a redispatch.

## Loop rules

- An execution root ARI refuses (unset `ARI_EXECUTION_ROOT`, the live checkout
  without `ARI_ALLOW_SELF_MODIFICATION=1`, or a path outside the configured root)
  stops the loop as `blocked` before any task exists.
- A step ARI did not dispatch stops the loop: `awaiting_approval` for an approval
  gate, `blocked` for anything else.
- A worker that raised after dispatch leaves its effect uncertain. The loop
  escalates and never retries it.
- A worker that returned a retryable failure may be retried as a new step, within
  the loop's `max_cycles` bound.

## Worker invocations

- `invoke_worker` is registered only in the adapter's own tool registry, for the
  workers the adapter was constructed with. Planners never see it and cannot
  propose one.
- It is `unbounded` for dispatch safety: once crossed, it can never be proven safe
  to redispatch.
- The worker runs with its working directory at the execution root, with a
  timeout from 1 to 3600 seconds.
- A worker cannot be dispatched under a `no network` restriction.

## Verification commands

Verification commands must resolve to an explicit command capability (see
[Execution Authority](execution-authority.md)). A profile command that is not a
capability, such as `python -c ...` or `pytest --version`, is refused by the
gateway and recorded as a failed check. It is never run another way.

## Known limits

- **Not OS containment.** Provider workers and `pytest` are arbitrary local code
  running as the OS user.
- **The acknowledgement is a shim.** It shows the step was handed off through the
  canonical protocol. It does not show that the worker process read anything.
- **Approval-gated worker steps resume only through the adapter.** The generic
  `resume-one` API uses the default tool registry, which has no `invoke_worker`, so
  it blocks such a step instead of running it.
- **Unverified steps stay open.** A `run_command` whose exit code is nonzero is
  recorded as `verification_failed` and left unresolved for
  [reconciliation](effect-reconciliation.md). Only succeeded steps are closed.
- **Duplicates across steps are not detected.** Each step is its own task, so a
  retry that repeats an earlier step's effect is governed by the loop's bounds, not
  by task-wide dispatch governance.
- **Paths still outside.** `ExecutionController.run()` (the one-step coding loop and
  approved retries), operator engine actions, the direct execution API/CLI
  endpoints, and `runtime/playground.py` do not yet use this path.
