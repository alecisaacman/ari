# Uncertain-Effect Reconciliation

The [Recovered Action Authority Gateway](recovered-action-gateway.md) fails closed
when an external action may have run but ARI cannot prove the outcome.
`EffectReconciler` (`modules/execution/reconciliation.py`) is how ARI later
records what actually happened. It changes what ARI knows about one action. It
never dispatches, retries, or approves anything.

## Eligibility

Reconciliation targets one exact persisted execution record. The request must
name its `task_id`, `execution_id`, `action_id`, and `action_digest`, and all of
them must match the stored row.

The execution's effective state, judged against the task's active attempt, must
be one of:

- `effect_may_have_occurred`: the dispatch raised, a crash left `executing` under
  a superseded attempt, or a superseded attempt reported late
- `verification_failed`: the tool returned, but ARI could not verify the intended
  effect
- `effect_confirmed_absent` that is **not** yet safe to redispatch. This applies
  when the absence was recorded without a landing proof, so it can be re-observed
  after landing is ruled out, or recorded as `effect_confirmed` when the late
  effect is found.

Everything else is refused:

- `executing` under the still-active attempt, because it may be in flight
- `failed_before_effect`, because it is already provably effect-free
- `succeeded`, `effect_confirmed`, and an absence that is already safe to
  redispatch
- terminal tasks
- requests from any attempt other than the task's active attempt
- a stale active attempt, meaning its lease expired outside a pause, approval,
  block, or waiting gate. Recover the worker session first.

## Outcomes

| Outcome | Execution state | Canonical checkpoint | Retry |
| --- | --- | --- | --- |
| `effect_confirmed` | `effect_confirmed` | step moves to completed with `reconciled: true`, `verified: false` | never re-dispatched, even after a plan revision |
| `effect_confirmed_absent` | `effect_confirmed_absent` | step stays pending; next action says a post-landing observation and a revision are required | only if the request carried the fence's landing token (`redispatch_safe`), then only through an explicit canonical plan revision |
| `inconclusive` | unchanged | no checkpoint; an event is recorded | still blocked |

ARI assesses the evidence. It does not take the requested outcome on trust:

- **Confirmed** requires at least one `effect_present` observation and no
  `effect_absent` observation.
- **Confirmed absent** opens a future retry path, so every observation must be
  `effect_absent` and at least one must cite a verifiable `reference`.
- Anything weaker or contradictory is recorded as `inconclusive`, and the
  assessment explains why.

Confirmed absence never retries by itself, and observed absence alone is not
enough to retry: the earlier dispatch might still land. An absence observed
before landing was ruled out stays insufficient after the dispatch ends: an
effect can land between the observation and the end.

`effect_confirmed_absent` stops governing the action only when **both** of these
hold. The full rule is in [Dispatch Safety Boundary](dispatch-safety.md#safe-to-redispatch).

- The reconciliation presented the fence's `landing_token`, which the reconciler
  obtained from `DispatchFences.rule_out_landing` **before** observing. The token
  exists only once ARI has established the dispatch can no longer land, which is
  never for `unbounded` effects such as `run_command`.
- The request is for a *different* digest, meaning a canonical plan revision
  followed by the normal gateway path, including any digest-bound approval.

The reserved digest stays denied. The record stores `redispatch_safe`, the bound
`landing_token`, and the `dispatch_fence_state` it saw. The gateway re-derives
safety live from the record and the fence. A later fence transition never
upgrades an earlier record. Migration `0006` reset every legacy record to
`redispatch_safe = 0`.

## Durability and audit

Each accepted request writes one row to `ari_execution_effect_reconciliations`.
The row records:

- the execution, decision, idempotency key, and reserving attempt
- the active attempt, plus the basis and resulting checkpoints
- the requested and assessed outcome
- the stored and effective previous state, and the resulting state
- `reconciled_by`, the reason, ARI's assessment, and the sanitized evidence with
  its SHA-256
- provenance and a timestamp

For a transition, the record, the compare-and-swap execution update (which also
sets `reconciliation_id`), the checkpoint, and the event all commit in one
immediate transaction.

- **Idempotent:** a byte-identical request (same identity, outcome, evidence,
  `reconciled_by`, reason, and landing token) returns the existing record and
  writes nothing.
- **Conflicting:** a different request against an already-reconciled execution
  is refused. Concurrent requests serialize on the immediate transaction, and the
  state compare-and-swap means at most one can transition.
- **Refused:** a refused or malformed request raises `ReconciliationRefused` and
  persists nothing.

## Late reports from superseded attempts

A superseded attempt can still finish its dispatch after reconciliation. The
gateway never lets that late report overwrite reconciled truth. It records an
`action.late_report_after_reconciliation` event, and:

- `effect_confirmed` stays confirmed
- `effect_confirmed_absent` returns to `effect_may_have_occurred`, because the late
  report contradicts confirmed absence. Any retry is blocked again until a new
  reconciliation.

## Known limits

- No API or operator surface exists yet. Callers use `EffectReconciler` directly.
- `reconciled_by` is a recorded claim. Proving the caller's identity remains an
  outer authentication concern, as it is for action approvals.
- Refused requests are not persisted, so their evidence is not retained.
- The landing token orders the observation only by the reconciler's attestation.
  ARI cannot verify when an external observation was made. If absence is
  confirmed wrongly, or attested falsely, a retry still duplicates the effect. See
  [Dispatch Safety Boundary](dispatch-safety.md).
