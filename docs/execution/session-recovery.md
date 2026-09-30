# Execution Session Recovery

ARI owns worker liveness and continuation state. A worker session is a leased
execution attempt, not a new task and not a new source of authority.

## State transitions

```text
waiting_for_worker
  -> active
  -> stale
  -> recovering
  -> awaiting_continuation_acknowledgement
  -> execution_ready
```

Orthogonal gates stop recovery: `awaiting_approval`, `paused`, `blocked`, and
`cancelled`. Terminal states are `succeeded`, `failed`, and `cancelled`.

The legacy `status` columns remain for compatibility. `lifecycle_state` is the
explicit session/recovery state.

## Lease and reconciliation rules

- ARI acquires the lease when the current controller starts an attempt.
- Only the lease owner can heartbeat.
- ARI's clock, not worker prose, determines whether a lease is stale.
- A healthy lease cannot be replaced.
- Pending approval, user pause, cancellation, and policy blocks are not worker
  failures and cannot trigger replacement.
- Reconciliation closes the stale attempt, records worker loss, creates one
  replacement attempt under the same `task_id`, and links it to the latest
  checkpoint and prior attempt.
- Reconciliation copies, but never widens, restrictions and authority state.

## Continuation handshake

ARI builds the continuation packet only from canonical task, checkpoint, and
attempt records. The replacement worker must acknowledge the objective,
completed work, pending work, restrictions, authority scope, and proposed next
action. ARI persists that acknowledgement before marking the replacement
attempt `execution_ready`.

Execution-ready does not mean execution resumed. This slice deliberately stops
before the next tool or side effect. `recovery_block_reason` records that the
unified authority/tool gateway is still required.
