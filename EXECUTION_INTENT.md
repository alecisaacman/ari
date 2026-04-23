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
- run a governed decision -> dispatch -> evaluation -> persistence loop
- invoke Codex as a local worker under ARI's control
- run bounded self-improvement cycles over the same worker seam
- switch between deterministic stub and real command-backed worker backends while keeping ARI as controller
- accept natural-language goals through the outward `ari` entrypoint
- choose higher-leverage bounded self-improvement slices using repo state, prior loop records, and current execution intent
- verify self-improvement slices with semantic verification profiles including changed paths, expected symbols, targeted tests, output checks, and unexpected-change detection
- persist a typed controller decision trail for each self-improvement cycle
- generate bounded action plans with likely files, structural targets, verification expectations, and retry refinement hints
- turn action plans into stronger worker prompts instead of thin goal handoffs
- derive typed controller decisions from signals before dispatch or alert handling

## What ARI cannot do yet
- generate good coding actions automatically from high-level goals
- run rich multi-step autonomous coding loops end to end across many milestones
- replace Codex as a builder

## Next objective
Build a stronger governed autonomous coding loop that can generate higher-quality bounded coding actions, refine retries from semantic verification failures, and carry a richer controller trajectory end to end.

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
