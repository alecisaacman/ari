# Topology

## Core Topology

- This repository contains the current canonical implementation of ARI's local-first brain and runtime.
- The local computer is the primary execution host for ARI today.
- SQLite is the current durable local system record.
- `ari-core` is the canonical state and logic owner.
- `ari-api` is the default contract into the brain.
- `ari-hub` is the primary interface surface.
- The current system includes real bounded execution, but not yet a full autonomous coding loop.
- The terminal-facing default identity is `ari`, which routes natural-language goals into canonical runtime paths.
- Codex is currently an external worker ARI can invoke locally inside bounded loops.

## Local-First Execution Model

ARI is designed as a local-first system.

Primary execution host:
- The user's local computer is the main execution environment.
- File access, command execution, and state mutation occur locally by default.

Future extension:
- Additional nodes such as mobile devices, remote workers, and cloud services may interface with the canonical brain.
- These nodes act as surfaces or extensions, not replacements for the core runtime.

Local-first does not mean single-machine forever.
It means:
- local control
- local execution by default
- external systems are optional extensions, not dependencies

## ARI And ACE

ARI:
- The core intelligence and authority
- Responsible for decision-making, execution, memory, and system state
- Lives in the canonical runtime

ACE:
- The ambient manifestation layer
- Surfaces information, context, and actions to the user
- May exist across multiple interfaces such as web, mobile, notifications, and voice

ACE does not replace ARI.
ACE exposes ARI to the user environment.
ARI remains the single source of authority.

## Surfaces

### Hub

The hub is the main visible window into ARI. It is a web surface hosted on the same home machine as the brain.

Responsibilities:

- show current operational state
- show current focus
- show blockers and approvals
- show important execution and coordination state
- support explainable inspection of why items were surfaced
- remain a client of canonical ARI state

### Terminal

The terminal is the operator surface for direct command, maintenance, and deep inspection.

Responsibilities:

- operational control
- direct state inspection and maintenance
- debugging and maintenance
- canonical CLI access into `ari-core`
- single outward invocation through `ari`
- stable response contracts that future hotkey, voice, and shortcut surfaces can reuse

### Phone

The phone is the mobile edge surface. It should expose the same underlying state through a reduced interface.

Responsibilities:

- glanceable awareness
- simple acknowledgements
- escalation handling
- future mobile hub access

### Notifications

Notifications are an escalation path, not a primary interface.

Responsibilities:

- carry only meaningful interruptions
- reference the underlying state or alert that triggered them
- remain explainable and reviewable after delivery

## Process Layout

- `ari-core`: canonical brain, persistence access, policy, coordination, execution
- `ari-api`: default service boundary for canonical reads, writes, and execution actions
- `ari-hub`: primary web surface and ambient interface
- notifications / phone / voice: future surfaces that should remain clients of the same canonical brain

## System Boundary

Current boundary:
- This repository defines the ARI core runtime.

Intended boundary:
- ARI operates as an intelligence layer across environments.
- The local machine is the primary host.
- Other surfaces are extensions, not separate brains.

This distinction matters:
ARI is not this repo.
This repo is the current implementation of ARI's brain.
