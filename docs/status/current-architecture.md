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
- compact lifecycle memory for bounded coding-loop chains
- docs-only skill design for future self-documentation/content creation
- docs-only readiness checklist for self-documentation content seeds
- read-only self-documentation content seed generator from git commit ranges
- static machine-readable skill catalog plus read-only skill-selection
  prototype for routing goals to known skills or missing-skill candidates
- read-only CLI inspection for the static skill catalog
- read-only skill-readiness evaluator for catalog promotion gates
- read-only missing-skill proposal generation for bounded future skill slices
- first ACE read-only dashboard shell in `services/ari-hub`

## Still evolving
- autonomous coding loop
- outbound notifications
- interface control
- universal shell helper
- Inspection Cabinet
- clean iOS / clean access points

## Important principle
External model providers should remain pluggable services, not the identity of the brain itself.

Native skills must follow `docs/skills/ari-native-skill-contract.md`: they plug
into ARI's shared memory, authority, validation, execution, verification,
inspection, explanation, and learning spine rather than becoming separate
brains. Current skill status is tracked in `docs/skills/skill-inventory.md`.

ACE read-only dashboard work must follow `docs/ace/read-only-dashboard-contract.md`.
