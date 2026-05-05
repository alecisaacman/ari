# One-Step Coding Loop Progress

Date: 2026-05-04

## Position

Overall ARI build estimate: 8.2/10.

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

## Boundary

ARI still runs at most one validated action through the existing bounded
execution path. Multi-step coding loops, repeated retry execution, automatic
approval, and UI approval controls remain future slices.

Coding-loop results are not persisted in a new store. If execution occurs, the
existing `ExecutionRun` lifecycle trace remains the durable inspection record.
If execution does not occur, the returned coding-loop inspection payload is the
authority explanation for why ARI stopped, asked, or rejected.

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

## Next Recommended Slice

Add durable coding-loop result persistence so non-executing outcomes, previews,
reviews, and approval lineage can be inspected without reconstructing them from
return payloads alone.
