# Hub Specification

## Role

The hub is the main visible window into ARI on the home computer. It is not the brain. It presents the current shared state and lets the operator inspect what ARI is tracking.

The hub may also support a narrow operator loop for maintaining canonical state through the API. It must remain API-backed and must not mutate persistence directly.

## Milestone 1 Hub Requirements

The hub should display:

- current operational state
- open loops requiring attention
- current trajectory against the week
- active signals
- active alerts and intelligence items
- one clear explanation pathway for surfaced items

The hub should also support simple actions to:

- set or update the current `DailyState`
- set or update the current `WeeklyState` planning and reflection fields
- add an open loop
- resolve an open loop

## Design Direction

- calm default tone
- concise copy
- strong information hierarchy
- minimal operator friction
- immediate clarity over visual flourish
- operational, not therapeutic
- JARVIS-like presence: quiet until something matters

## Information Sections

### Now

Shows the current `DailyState`:

- top priorities
- win condition
- movement recorded or not recorded
- stress level when available
- next action

### Open Loops

Shows unresolved loops with priority, due date, and project context.

### Trajectory

Shows the current `WeeklyState`:

- outcomes
- cannot drift commitments
- blockers
- lesson when available

### Signals

Shows what ARI thinks is changing in the system and why, with direct evidence.

The hub should support a simple drill-down into one surfaced signal so the operator can inspect:

- reason
- structured evidence items
- related entity references when present

### Alerts / Intelligence

Shows escalations and high-value surfaced items with the reason they were elevated.

The hub should support a simple drill-down into one surfaced alert so the operator can inspect:

- reason
- source signal ids
- the linked source signal evidence chain through the API

The hub should feel like an operating console, not a wellness dashboard.

## Non-Goals For Sprint 1

- complex editing workflows
- heavy customization
- real-time collaboration
- polished mobile parity

Simple same-page forms and post/redirect/get flows are in scope when they reuse the canonical API/state seam without adding local business logic.
