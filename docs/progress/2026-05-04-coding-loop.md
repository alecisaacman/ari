# One-Step Coding Loop Progress

Date: 2026-05-04

## Position

Overall ARI build estimate: 8.5/10.

This slice upgrades the existing one-step coding loop seam. It does not add broad
autonomy, approval mutation, arbitrary shell access, or multi-step execution.

## What Changed

- The one-step coding loop now returns `requires_approval` when the selected
  preview action is authority-gated.
- Approval-required actions preserve the plan preview for inspection and do not
  call the execution controller run path.
- Verification failures after one executed action are classified as
  `retryable_failure` when the action ran but verification did not pass.
- Retry proposals are deterministic and inspectable. They include the failure
  reason, failed verification summary, suggested next goal/action, and whether
  approval would be required.
- Retry proposals are only proposals. They do not execute.
- Coding-loop results are exposed through the existing execution CLI/API
  inspection family. The normalized inspection payload shows status, reason,
  preview id, execution-run id, whether execution occurred, approval reason,
  retry proposal, suggested retry goal/action, and retry approval requirement.
- Retry proposals now produce a pending retry-approval artifact. The artifact
  preserves the source coding-loop result, preview id, failed execution-run id,
  original goal, proposed retry goal/action, failed verification summary, and a
  pending `ApprovalRequirement`.
- Pending retry-approval artifacts can be stored durably and marked approved or
  rejected through typed mutation seams. Mutation preserves the original
  proposal and source references and records terminal approval state.
- Durably approved retry-approval artifacts can now execute exactly one retry
  through the existing bounded execution controller. Execution records the
  retry `ExecutionRun` id, execution status, reason, and timestamp back onto
  the durable approval artifact.
- Approved retry execution can now be captured into session memory and
  explained through the existing memory explanation spine. The explanation
  links the original failed execution, approval artifact, retry execution run,
  failed verification summary, proposed retry, authority state, and final retry
  status.
- Approved retry execution can now be reviewed through a read-only post-run
  classification artifact. The review decides whether ARI should stop, block,
  mark unsafe, ask the user, or propose another bounded approval item without
  executing anything.
- `propose_retry` post-run reviews can now be converted into a new durable
  pending retry-approval artifact. The new approval links back to the prior
  retry approval and prior retry execution run, while the prior approval records
  the next approval id to prevent silent duplication.
- Coding-loop lifecycle results are now persisted durably in the coordination
  SQLite store as compact records. The records preserve non-executing outcomes,
  preview and execution-run links, retry proposals, retry approval status,
  retry execution summaries, post-run reviews, and next-approval lineage without
  duplicating full `ExecutionRun` payloads.
- Coding-loop results can now be listed and shown through the existing
  execution CLI/API inspection family.
- Post-run retry reviews now have an explicit loop-continuation policy. The
  policy decides whether a review is eligible to create exactly one pending
  follow-up approval, or whether ARI should stop, block, ask, mark unsafe,
  report not-executed, or reject a duplicate continuation.
- Coding-loop retry approval chains can now be inspected as one bounded story.
  The chain view starts from a root coding-loop result, walks retry approvals
  through prior/next lineage, includes post-run reviews and continuation
  decisions, and reports a terminal chain status without executing anything.
- Coding-loop retry chains can now be advanced by at most one approved,
  unexecuted retry approval. Advancement loads the chain, requires the terminal
  status to be `executable_approved_retry_available`, executes exactly that
  approved retry through the existing boundary, refreshes the chain, and stops.
- The latest pending retry approval in a coding-loop chain can now be approved
  or rejected from the root coding-loop result id. These chain-level controls
  resolve the latest pending approval and delegate to the existing approval
  mutation boundary.
- Eligible `propose_retry` reviews can now create the next pending retry
  approval from the root coding-loop result id. The chain-level proposal command
  resolves the eligible reviewed approval and delegates to the existing
  next-approval creation boundary.

## Boundary

ARI still runs at most one validated action through the existing bounded
execution path. Multi-step coding loops, repeated retry execution, automatic
approval, and UI approval controls remain future slices.

Coding-loop results are persisted as compact lifecycle records. If execution
occurs, the existing `ExecutionRun` lifecycle trace remains the durable source
for detailed execution data; coding-loop persistence stores references and
summaries so inspection does not duplicate the execution trace.

Retry-approval artifacts are boundary records only. They do not grant approval,
execute the retry, or start a retry loop.

Retry approvals are now persisted in the existing coordination SQLite store as
`ari_runtime_coding_loop_retry_approvals`. CLI/API inspection and mutation are
available for retry approvals.

Approved retry execution is a separate boundary from approval mutation. A retry
can execute only when the durable approval exists, is approved, has not already
executed, and can be reconstructed as a normal `ExecutionGoal` through the
existing bounded execution controller. Pending or rejected retry approvals do
not execute. Already executed approvals do not execute again. Unsafe retry
goals still fail closed through the existing planner, validation, and command
policy path.

Retry-execution memory capture is explanatory only. It does not execute,
approve, reject, or mutate retry proposals beyond creating an idempotent
session memory block for the already-existing retry approval.

Post-run retry execution review is also explanatory/control-only. A
`propose_retry` review does not create a new approval artifact and does not
execute. It only exposes the next bounded control decision for a later approval
slice.

Creating a follow-up approval from a `propose_retry` review is still an
approval-boundary operation. It does not approve or execute the follow-up
retry. It only creates the next pending authority artifact.

Loop-continuation policy is inspection/control-only. It does not execute,
approve, or retry. It only makes the next-approval eligibility decision typed
and visible before the existing propose-next mutation is allowed to create a
single pending approval artifact.

Retry-chain inspection is read-only and bounded by a maximum traversal depth.
It links to existing `ExecutionRun` and retry-approval records instead of
duplicating full execution traces.

Chain advancement is bounded and authority-gated. It does not approve pending
items, execute rejected items, create follow-up approvals, or loop. If the chain
is pending, rejected, stopped, unsafe, blocked, ask-user, truncated, cyclic, or
otherwise incomplete, advancement returns a no-action/rejected result without
execution.

Chain-level approve/reject controls are convenience-only. They do not create new
approval semantics, advance the chain, or execute retries. They refuse unknown,
truncated, cyclic, stopped, unsafe, blocked, ask-user, or non-pending chains.

Chain-level propose-next controls are also convenience-only. They do not approve,
execute, or advance. They create exactly one pending approval only when the
latest reviewed retry is eligible for `propose_retry`, and refuse duplicate or
non-eligible chains.

## Next Recommended Slice

Add a compact chain lifecycle summary for memory capture so ARI can learn from
bounded coding-loop outcomes without duplicating full execution traces.
