# ARI Phase Log

## v0.9-core-converged
- Canonical brain moved into `services/ari-core`
- API contract established in `services/ari-api`
- Hub converged into `services/ari-hub`
- Imports removed
- Hub-to-brain seam made API-first
- Execution layer added for bounded coding actions
- Operator lifecycle and verification became real

## Current state
ARI is now:
- architecturally converged
- API-driven
- execution-capable
- not yet a full autonomous coding loop

## Next milestone
v1.0-autonomous-coding-loop

Goal:
- generate coding actions
- execute
- verify
- retry intelligently
- stop on success or clean failure
