# Topology

## Core Topology

- The home computer hosts the ARI brain.
- Postgres is the durable system record.
- Shared typed state models define the canonical data contract.
- The orchestration layer reads canonical state, evaluates signals, persists signals, and emits durable alerts.

## Surfaces

### Hub

The hub is the main visible window into ARI. It is a web surface hosted on the same home machine as the brain.

Responsibilities:

- show current operational state
- show open loops
- show trajectory against the week
- show important signals and alerts
- support explainable inspection of why items were surfaced

### Terminal

The terminal is the operator surface for direct command, maintenance, and deep inspection.

Responsibilities:

- operational control
- direct state inspection
- routine execution
- debugging and maintenance

### Phone

The phone is the mobile edge surface. It should expose the same underlying state through a reduced interface.

Responsibilities:

- glanceable awareness
- simple acknowledgements
- escalation handling

### Notifications

Notifications are an escalation path, not a primary interface.

Responsibilities:

- carry only meaningful interruptions
- reference the underlying state or alert that triggered them
- remain explainable and reviewable after delivery

## Process Layout

- `ari-core`: background routines, orchestration, drift detection, alert generation
- `ari-api`: service boundary for state, events, and explainability queries
- `ari-hub`: primary web surface
- shared packages: typed state, persistence, events, routines, signals, CLI
