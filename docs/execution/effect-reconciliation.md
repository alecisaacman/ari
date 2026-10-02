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

Everything else is refused:

- `executing` under the still-active attempt, because it may be in flight
- `failed_before_effect`, because it is already provably effect-free
- `succeeded`, and any execution that has already been reconciled
- terminal tasks
- requests from any attempt other than the task's active attempt
- a stale active attempt, meaning its lease expired outside a pause, approval,
  block, or waiting gate. Recover the worker session first.

## Outcomes

| Outcome | Execution state | Canonical checkpoint | Retry |
| --- | --- | --- | --- |
| `effect_confirmed` | `effect_confirmed` | step moves to completed with `reconciled: true`, `verified: false` | never re-dispatched, even after a plan revision |
| `effect_confirmed_absent` | `effect_confirmed_absent` | step stays pending; next action says a revision is required | eligible only through an explicit canonical plan revision |
| `inconclusive` | unchanged | no checkpoint; an event is recorded | still blocked |

ARI assesses the evidence. It does not take the requested outcome on trust:

- **Confirmed** requires at least one `effect_present` observation and no
  `effect_absent` observation.
- **Confirmed absent** opens a future retry path, so every observation must be
  `effect_absent` and at least one must cite a verifiable `reference`.
- Anything weaker or contradictory is recorded as `inconclusive`, and the
  assessment explains why.

Confirmed absence never retries by itself. The reserved digest stays denied.
Like `failed_before_effect`, `effect_confirmed_absent` stops governing the action
only for a *different* digest, which means a canonical plan revision followed by
the normal gateway path, including any digest-bound approval.

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
  `reconciled_by`, and reason) returns the existing record and writes nothing.
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
- If confirmed absence is followed by a revised-digest retry, and only then a
  superseded attempt's original dispatch lands, the action has run twice. ARI
  reopens the original record and records the late report, but cannot undo the
  effect. Confirming absence while a superseded worker may still be alive is the
  reconciler's risk to judge.
