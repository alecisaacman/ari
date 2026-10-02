# Dispatch Safety Boundary

This document says what ARI can and cannot guarantee once a recovered action
reaches its external effect. Code: `modules/execution/dispatch.py` and the dispatch
section of `RecoveredActionGateway.resume_one`.

## The real effect boundary

A recovered action reaches its effect through one in-process, synchronous call:
`RecoveredActionGateway.resume_one` → `action_executor` (default `execute_action`)
→ `ExecutionRoot`. Today that call can only:

- write or patch a file under the execution root
- run an allowlisted subprocess (`pytest`, `ls`, `cat`) with `subprocess.run`

There is no network provider, no provider idempotency key, no provider-side
reference, and no cancellation API. Dispatch is not centralized: it runs in
whichever process calls `resume_one`. The controller, engine, coding loop, and
direct API endpoints still call `execute_action` without this boundary.

## What ARI guarantees

The honest guarantee is: **at most one ARI-authorized dispatch per logical
action is ever in progress, a new dispatch never starts until every earlier
dispatch of that action has been proven unable to land, and anything ARI cannot
prove fails closed into reconciliation.** It is not exactly-once. Two effects can
still happen when evidence wrongly confirms absence of an effect that already
landed, and ARI cannot undo an effect.

### A. Pre-dispatch safety

Every reservation issues a durable **dispatch fence**. A fence carries the
execution, logical action, digest, attempt, a monotonic per-action
**generation**, its state, and timestamps.

A fence crosses into the effect only if all of these hold:

- the logical action's dispatch lock is held
- every gateway check passes again in one transaction: lifecycle, active
  attempt, worker/session, lease, approval, and pause
- the fence matches the exact execution, action, digest, and attempt
- the fence is still `issued`
- it is the newest generation
- no earlier fence of the action is still `crossing`

Crossing (`issued → crossing`) and `executing` commit together. A fence crosses
at most once.

### B. In-flight safety

ARI cannot stop an effect that has crossed. Supersession, pause, or
reconciliation arriving after the crossing commit do not stop it.

What ARI enforces instead is the **dispatch lock**: an exclusive OS `flock` on
one file per logical action `(task_id, action_id)`. It is held from the final
check, through the effect, until the dispatch is recorded as `returned`:

- Subprocesses inherit the lock's descriptor, so it stays held while a child
  outlives a killed parent.
- Release only closes the descriptor, never `LOCK_UN`.
- The kernel releases the lock when every holder has exited.

### C. Provider-side idempotency

None of the current tools supports it, so ARI does not claim it. ARI's
idempotency key is internal to ARI. When a provider with real idempotency keys
exists, the stable logical identity to send is the execution's
`idempotency_key`, tied to its fence generation.

### D. Post-dispatch reconciliation and quiescence

[Reconciliation](effect-reconciliation.md) records whether an effect is observed
present or absent. Observed absence is **not** enough to redispatch, because an
earlier dispatch might still land. Redispatch also needs a **quiescent fence**,
which can come from three places:

- `returned`: the dispatch call returned, and that was recorded while the lock
  was still held
- `quiesced`: `DispatchFences.prove_quiescent` acquired the action's lock while
  the fence was `crossing`, which means no process or inheriting child is still
  inside that dispatch
- `revoked`: the fence never crossed

If the lock is held, the proof fails closed with `DispatchQuiescenceUnproven`.
The gateway re-derives this on every proposal. `effect_confirmed_absent` stops
governing a logical action only when its fence is quiescent. A missing fence
counts as not quiescent.

## Time-of-check/time-of-use windows

| Window | Outcome |
| --- | --- |
| gate → reservation | reservation re-checks checkpoint and attempt in one transaction |
| reservation → lock | the lock is busy or the fence was revoked: stop before effect |
| lock → crossing commit | rechecked in the crossing transaction; nothing that matters can revoke while the lock is held |
| crossing commit → syscall | **not closable**: the effect proceeds; supersession only blocks the *next* dispatch |
| effect → `returned` record | a crash leaves `crossing`; quiescence is provable once the lock is free |
| `returned` → result persistence | a crash leaves `executing`; the fence is already `returned`, so absence alone makes it eligible |

## Limits that cannot be solved generically

- **One host only.** `flock` excludes processes on one host and is unreliable on
  network filesystems. ARI's SQLite ledger is single-host as well.
- **Escaping processes.** A grandchild that closes inherited descriptors, or
  daemonizes, can outlive the lock.
- **Hung holders.** A hung or stopped holder keeps the lock held forever.
  Quiescence then stays unproven until an operator ends the process.
- **Wrong evidence.** If an effect landed before absence was observed,
  reconciliation is wrong and a retry duplicates the effect. The dispatch's
  recorded outcome is kept on the fence for the reconciler to weigh.
- **Remote effects.** A request that has left the host cannot be recalled. A
  future network provider needs provider idempotency keys, or a provider-side
  status query, on top of this boundary.
