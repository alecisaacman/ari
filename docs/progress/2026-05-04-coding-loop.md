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

## Boundary

ARI still runs at most one validated action through the existing bounded
execution path. Multi-step coding loops, retry execution, approval mutation,
and UI/API approval controls remain future slices.

## Next Recommended Slice

Add approval-aware inspection through existing CLI/API surfaces for coding-loop
results, then add an explicit approved retry execution boundary.
