# ARI Execution Intent

## Current milestone
v0.9-core-converged

## What ARI can do now
- persist canonical memory and tasks
- coordinate through a canonical API
- execute bounded coding actions
- mutate files safely
- run allowlisted verification commands
- persist execution lifecycle
- surface execution state in the hub

## What ARI cannot do yet
- generate good coding actions automatically from high-level goals
- retry intelligently after failure
- run full multi-step coding loops
- replace Codex

## Next objective
Build the autonomous coding loop engine.

## Success criteria
Given a coding goal, ARI can:
1. generate a candidate action
2. apply the change
3. run verification
4. analyze result
5. retry intelligently
6. stop on success or clean failure

## Non-goals for this step
- arbitrary shell access
- destructive system operations
- large multi-file semantic refactors
- full unattended autonomy
