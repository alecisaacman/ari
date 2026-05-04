# One-Step Coding Loop Progress

Date: 2026-05-04

## Position

Overall ARI build estimate: 7.1/10.

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
- Pending retry-approval artifacts can be marked approved or rejected through a
  typed in-memory mutation seam. Mutation preserves the original proposal and
  source references and records terminal approval state.

## Boundary

ARI still runs at most one validated action through the existing bounded
execution path. Multi-step coding loops, retry execution, approval mutation,
and UI/API approval controls remain future slices.

Coding-loop results are not persisted in a new store. If execution occurs, the
existing `ExecutionRun` lifecycle trace remains the durable inspection record.
If execution does not occur, the returned coding-loop inspection payload is the
authority explanation for why ARI stopped, asked, or rejected.

Retry-approval artifacts are boundary records only. They do not grant approval,
execute the retry, or create approve/reject commands.

Retry-approval mutation is in-memory only in this slice. ARI does not yet expose
durable lookup, approve, or reject commands for retry approvals because these
artifacts are returned with the coding-loop result rather than persisted in a
dedicated approval registry.

## Next Recommended Slice

Add approval-aware inspection through existing CLI/API surfaces for coding-loop
results, then add an explicit approved retry execution boundary.
