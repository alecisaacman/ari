# Dispatch Safety Boundary

This document says what ARI can and cannot guarantee once a recovered action
reaches its external effect, and exactly when ARI treats a retry as safe. The
code is in `modules/execution/dispatch.py`, the dispatch section of
`RecoveredActionGateway.resume_one`, `RecoveredActionGateway._select_governing`,
and `EffectReconciler`.

## The real effect boundary

A recovered action reaches its effect through one in-process, synchronous call:
`RecoveredActionGateway.resume_one` → `action_executor` (default `execute_action`)
→ `ExecutionRoot`. Today that call can only:

- read, write, or patch a file under the execution root, in the calling thread
- run an allowlisted subprocess (`pytest`, `ls`, `cat`) with `subprocess.run`

There is no network provider, no provider idempotency key, no provider-side
reference, and no cancellation API. Dispatch is not centralized: it runs in
whichever process calls `resume_one`. The controller, engine, coding loop, and
direct API endpoints still call `execute_action` without this boundary.

## Four facts that are not the same

| Fact | Recorded as | Proves |
| --- | --- | --- |
| The dispatch call returned | fence `returned` | the dispatching call ended. It does **not** prove that a subprocess's descendants ended. |
| The dispatch lock was acquired after a crossing | fence `lock_released` (formerly `quiesced`) | no process still holding *that lock inode* is inside the dispatch. A descendant that never held the lock, or closed it, can still be running. |
| The effect can no longer land | fence `landing_token` is set | established only for effect classes that support it (see below) |
| **Safe to redispatch** | derived live by the gateway | the effect is absent **and** that absence was observed after the effect could no longer land |

Earlier versions treated the first two as the third, and treated "absence
observed at some time" plus "terminality observed later" as the fourth. Neither
holds.

## Effect terminality

Every fence records an `effect_terminality`, chosen at reservation:

- **`in_process`**: the built-in `read_file`, `write_file`, and `patch_file`
  actions. `execute_action` performs them synchronously in the dispatching thread.
  Once that call has returned, or the dispatching process is gone, the effect
  cannot land later.
- **`unbounded`**: everything else. That includes `run_command`, any injected
  `action_executor` that does not declare a classifier, and legacy fences without
  a classification. A subprocess can start a detached grandchild that closes
  inherited descriptors, daemonizes, or queues asynchronous work. That descendant
  can produce the effect after the direct child returns, after a `subprocess.run`
  timeout kills the child, and after the lock is free. ARI cannot observe this
  generically.

`RecoveredActionGateway(effect_terminality=...)` lets an injected executor declare
its classification. Declaring `in_process` asserts that the executor never starts
threads, processes, or remote work that outlive the call.

## When landing is ruled out

A fence earns a one-time, unique `landing_token` (and `landing_ruled_out_at`)
only in these cases:

- **`revoked`**: the fence never crossed. Stop-before-effect and superseded
  reservations revoke unused fences, and revocation is a compare-and-swap against
  crossing.
- **`returned`** for an `in_process` effect. The token is written in the same
  transaction that records the return, while the dispatcher still holds the lock.
- **`lock_released`** for an `in_process` effect. `DispatchFences.rule_out_landing`
  acquires the exact lock inode the dispatcher recorded when crossing. Success
  means the dispatching process has exited or closed the lock, for example after
  a SIGKILL.

For an `unbounded` effect, `rule_out_landing` always fails with
`DispatchLandingUnproven` once the fence has crossed. It also fails closed when
the lock is held, when the lock file is missing, or when the lock file is not the
inode the dispatcher held.

## Safe to redispatch

A logical action `(task_id, action_id)` may dispatch under a revised digest only
when every earlier execution of it either:

- stopped before effect (`failed_before_effect`, revoked fence), or
- is **safe to redispatch**: its state is `effect_confirmed_absent`, and the
  reconciliation that set it presented the fence's `landing_token`
  (`redispatch_safe = 1`, and the record's token equals the fence's token).

The ordering proof is the token. It does not exist until landing is ruled out,
and the reconciler must obtain it **before** gathering the evidence it submits.
The protocol is:

1. `proof = DispatchFences.rule_out_landing(...)`. This fails closed if landing
   cannot be ruled out.
2. Observe the target resource.
3. `EffectReconciler.reconcile(..., landing_token=proof.landing_token)`.

An absence recorded without the token is stored as a true observation of that
moment. It never becomes safe later, whatever happens to the fence. A stale
`effect_confirmed_absent` can be reconciled again: with a bound absence
observation, or as `effect_confirmed` when the late effect is found. Any
`observed_at` timestamp earlier than `landing_ruled_out_at` makes the request
inconclusive. That wall-clock check is supplementary, never the proof. A token
from another fence is refused.

Presenting the token is the reconciler's attestation that the observation came
afterwards. ARI cannot verify when an external observation was made, any more
than it can verify the evidence itself.

### Renamed actions

ARI cannot tell whether a differently named action repeats an earlier action's
effect. While any execution in the task is unresolved, no other action in that
task may reserve a dispatch. Unresolved means `authorized_not_run`, `executing`,
`effect_may_have_occurred`, `verification_failed`, or `effect_confirmed_absent`
without being safe to redispatch. Before this rule existed, renaming the pending
action dispatched the same effect a second time, while the original was still
crossing. Effects repeated across *different tasks* are not detected.

### What each action type can prove today

| Action type | Can become safe to redispatch after crossing? |
| --- | --- |
| `write_file`, `patch_file`, `read_file` via the built-in executor | yes: returned, or lock inode acquired, then a bound absence observation |
| `run_command` | **no**. It stays blocked until reconciled as `effect_confirmed`. |
| injected executor without a classifier | **no** |
| any action whose fence never crossed | yes: `failed_before_effect`, unchanged |

## What ARI guarantees

The honest guarantee is:

> ARI never starts a dispatch of a logical action, or of any other action in the
> same task, while an earlier crossed dispatch of that action is unresolved, unless
> ARI established that the earlier dispatch can no longer produce its effect *and*
> an absence observation was bound to that establishment. Anything ARI cannot
> establish fails closed.

It is **not exactly-once**. Two effects can still happen when:

- a reconciler wrongly reports absence of an effect that is present
- a reconciler attests to a post-landing observation that was really made earlier
- an injected executor wrongly declares `in_process`
- something outside this boundary (another task, the controller, the coding loop,
  the API) performs the same effect

ARI cannot undo an effect.

### Pre-dispatch safety

Every reservation issues a durable fence carrying the execution, logical action,
digest, attempt, a monotonic per-action generation, effect terminality, state, and
timestamps. A fence crosses into the effect only if all of these hold:

- the logical action's dispatch lock is held, on the inode currently at the lock
  path
- every gateway check passes again in one transaction: lifecycle, active attempt,
  worker/session, lease, approval, and pause
- the fence matches the exact execution, action, digest, and attempt
- the fence is still `issued`
- it is the newest generation
- no earlier fence of the action is `crossing`, `returned`, or `lock_released`
  without a landing token

Crossing (`issued → crossing`), the lock identity (path, device, inode), and
`executing` commit together. A fence crosses at most once.

### In-flight behavior

ARI cannot stop an effect that has crossed. Supersession, pause, or
reconciliation arriving after the crossing commit do not stop it. They only block
the next dispatch.

The dispatch lock is an exclusive OS `flock` on one file per logical action. It is
held from the final check, through the effect, until the dispatch is recorded as
`returned`. Subprocesses inherit its descriptor, and release only closes it
(never `LOCK_UN`), so an inheriting child keeps it held. The lock is a local
mutual-exclusion tool and the mechanism behind `lock_released`. It proves nothing
about processes that do not hold it.

## Lock identity

- The lock directory is `<canonical database directory>/dispatch-locks`. The path
  is resolved, so symlinked and relative paths to one database share one lock
  directory.
- Acquisition verifies that the locked descriptor's inode is still the file at
  the path. If the file was unlinked or replaced between `open` and `flock`, the
  acquisition is refused.
- The crossing records the held inode. `rule_out_landing` opens that recorded
  path without creating it and requires the same device and inode. If the lock
  file or directory was deleted or recreated, the proof fails closed permanently,
  because the original inode cannot be reopened. Inode reuse is not a hole: an
  inode number is reused only after the original file has no open descriptor,
  which means no holder remains.
- Hard links to the database derive a different lock directory. SQLite does not
  support them either. Proofs still check the recorded inode, and crossings are
  still serialized by the database.

## Time-of-check/time-of-use windows

| Window | Outcome |
| --- | --- |
| gate → reservation | reservation re-checks checkpoint, attempt, and task-wide governance in one transaction |
| reservation → lock | the lock is busy or replaced, or the fence was revoked: stop before effect |
| lock → crossing commit | rechecked in the crossing transaction |
| crossing commit → syscall | **not closable**: the effect proceeds. Supersession only blocks the *next* dispatch. |
| effect → `returned` record | a crash leaves `crossing`. Landing can be ruled out only for `in_process`, by acquiring the recorded lock inode. |
| `returned` → result persistence | a crash leaves `executing`. An `in_process` fence already has its token, but a bound absence observation is still required. |
| absence observed → landing ruled out | the absence is stale and never qualifies |

## Limits that cannot be solved generically

- **One host only.** `flock` excludes processes on one host and is unreliable on
  network filesystems. ARI's SQLite ledger is single-host as well.
- **Escaping processes.** This is why `run_command` is `unbounded` and never safe
  to redispatch once it has crossed.
- **Hung holders.** A hung or stopped holder keeps the lock held, and landing
  stays unproven until an operator ends the process.
- **Deleted lock files.** A crossing fence whose lock file was deleted can never
  be proven. Its action stays blocked; no operator override exists yet.
- **Wrong or misattested evidence.** This is described above.
- **Remote effects.** A request that has left the host cannot be recalled. A
  future network provider will need provider idempotency keys, or a
  provider-side status query, plus its own terminality classification.
