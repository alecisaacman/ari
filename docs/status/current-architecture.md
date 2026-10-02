# Current Architecture

## Core Rule
- ARI is the brain
- ACE is the interface / hub

## Services
- `services/ari-core` — canonical runtime and intelligence core
- `services/ari-api` — API contract over canonical capabilities
- `services/ari-hub` — interface surface and client

## Canonical in ARI
- notes
- tasks
- structured memory
- coordination state
- policy / derivation
- execution layer for bounded coding actions
- durable execution tasks, worker attempts, ordered events, append-only
  checkpoints, and normalized terminal results
- ARI-owned worker leases, heartbeats, stale-attempt reconciliation,
  continuation packets, and persisted continuation acknowledgements
- ARI-owned recovered-action proposals, action-bound approvals, explicit resume
  decisions, idempotency reservations, result persistence, and verification
- compact lifecycle memory for bounded coding-loop chains
- self-documentation/content creation skill design and readiness docs
- read-only self-documentation content seed generator from git commit ranges
- read-only self-documentation content package generator from ContentSeed JSON
- durable local persistence and CLI inspection for self-documentation
  ContentSeed and ContentPackage artifacts
- static machine-readable skill catalog plus read-only skill-selection
  prototype for routing goals to known skills or missing-skill candidates
- read-only CLI inspection for the static skill catalog
- read-only skill-readiness evaluator for catalog promotion gates
- read-only missing-skill proposal generation for bounded future skill slices
- ARI-owned read-only overview model exposed through CLI and API inspection
- first ACE read-only dashboard shell in `services/ari-hub`, backed by the
  ARI-owned overview model when available

## Still evolving
- provider-capability routing and automatic worker failover
- autonomous coding loop
- outbound notifications
- interface control
- universal shell helper
- Inspection Cabinet
- clean iOS / clean access points

## Important principle
External model providers should remain pluggable services, not the identity of the brain itself.

The existing bounded controller now records continuous ARI-owned state at plan,
risky-operation, action-result, verification, and terminal boundaries. This is a
continuity ledger, not yet a provider router or automatic failover engine.

The current single backend now runs inside an ARI-owned leased session. ARI can
declare an expired worker stale, create a linked replacement attempt, reconstruct
continuation state, and require acknowledgement. Recovery reaches
`execution_ready`, then the recovered-action gateway can authorize and execute
exactly one pending action. It checkpoints before dispatch, persists and verifies
the result, and returns control to ARI before any next action. An effect the
gateway cannot prove stays blocked until evidence-backed reconciliation records it
as confirmed, confirmed absent, or still inconclusive. Reconciliation never retries.
A per-action dispatch fence and OS lock keep dispatches of one action from
overlapping. Absence permits a retry only after the earlier dispatch is proven
quiescent. ARI does not claim exactly-once external effects.

Native skills must follow `docs/skills/ari-native-skill-contract.md`: they plug
into ARI's shared memory, authority, validation, execution, verification,
inspection, explanation, and learning spine rather than becoming separate
brains. Current skill status is tracked in `docs/skills/skill-inventory.md`.

ACE read-only dashboard work must follow `docs/ace/read-only-dashboard-contract.md`.
