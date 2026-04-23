# ARI — Agentic Recursive Intelligence

ARI is a personal intelligence system designed to move from passive AI assistance to active execution.

**ARI is the brain. ACE is the interface.**

## Core Identity

ARI is not a single application or folder.

This repository contains the current canonical implementation of ARI's local-first brain and runtime.

ARI itself is a local-first intelligence system designed to operate across surfaces and devices, beginning with the user's primary computer as the execution host.

The code in this repository is the source-of-truth implementation of ARI's core loop, decision system, and execution capabilities. It should be treated as the canonical brain, not the full boundary of the system.

## What this repository contains

- `services/ari-core` — canonical runtime / brain
- `services/ari-api` — API contract over canonical capabilities
- `services/ari-hub` — ACE hub surface

## Current capabilities

ARI now has:
- canonical notes, tasks, and structured memory
- canonical coordination and policy state
- API-first hub-to-brain architecture
- bounded coding/operator execution
- execution lifecycle tracking and verification
- a governed decision, dispatch, evaluation, and persistence loop
- a canonical decision layer that turns signals into typed act / escalate / defer / ignore decisions with explicit reasoning
- a local-first worker backend seam controlled by ARI, with deterministic stub and real command-backed modes
- a bounded self-improvement runner over the same worker seam
- a single outward `ari` CLI entrypoint with natural-language routing
- controller-quality self-improvement slice selection tied to repo state and execution intent
- stronger self-improvement verification using repo evidence and explicit verification commands
- persisted controller decision records for each self-improvement cycle
- semantic verification profiles with slice-aware checks instead of generic success heuristics
- bounded action plans that give Codex concrete local tasks, structural targets, and retry guidance under ARI control

## Current milestone

**v0.12 — Bounded action generation**

This means:
- the real brain is canonical
- the API seam is real
- the hub is no longer the brain
- execution is now a real capability
- ARI can invoke Codex as a worker inside ARI's own bounded loop
- the terminal surface now starts from one outward identity: `ari`
- ARI leaves a typed controller trail for bounded self-improvement cycles
- bounded self-improvement no longer trusts plausible stdout alone
- ARI now generates explicit bounded action plans and tighter retry prompts for Codex worker runs
- ARI can switch between stub and real worker backends without changing the controller loop or outward `ari` identity

## Next milestone

**v1.0 — Governed Autonomous Coding Loop**

Goal:
- generate coding actions
- execute them
- verify results
- retry intelligently
- move ARI toward replacing external coding agents over time

## Direction

Long-term, ARI is being built toward:
- a coding/operator system that can gradually replace Codex-like workflows
- persistent self-documentation
- premium multi-surface access
- a future Inspection Cabinet
- clean iOS and clean access points

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

## Repository layout

- `services/ari-core/`
- `services/ari-api/`
- `services/ari-hub/`
- `config/schema.sql`
- `tests/`
- `docs/`

## Working rule

Keep ARI canonical.  
Keep ACE thin.  
Keep external providers pluggable.  
If a capability belongs to the brain, move it inward.

## Surface Simplicity

ARI is the outward identity.

The terminal-facing default should be:
- one invocation surface
- one response contract
- one canonical authority

Codex is a worker under ARI's control, not the controller of the system.
The worker seam is pluggable, but the controller remains canonical inside ARI.
