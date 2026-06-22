# Repository Structure

## Principle

This repository is organized around canonical services first.

ARI is not a single application or folder.

This repository contains the current canonical implementation of ARI's local-first brain and runtime.

The main architecture rule is:

- `ari-core` owns canonical logic and state
- `ari-api` is the default contract
- `ari-hub` is the surface

Legacy or experimental packages may still exist, but they are not the source of truth unless the current docs explicitly say so.

## Repository Role

This repository represents the canonical ARI core.

It currently contains:
- the decision loop
- execution layer
- orchestration
- persistence
- evaluation and control logic
- a natural-language terminal entry surface for ARI

It does not represent the full ARI system boundary.

Future surfaces and nodes such as UI, mobile, and integrations are expected to interface with this core through defined contracts, but are not part of the core runtime itself.

## Top Level

- `README.md`: project overview and startup path
- `AGENTS.md`: future-agent execution rules for this repository
- `docs/`: architecture source of truth
- `services/`: runnable service surfaces
- `packages/`: supporting or legacy shared modules where still relevant
- `tests/`: verification
- `compose.yaml`: local infrastructure baseline
- `pyproject.toml`: Python tooling baseline
- `config/schema.sql`: canonical SQLite schema

## Services

### `services/ari-core`

Canonical ARI brain.

Owns:

- memory
- tasks
- notes
- policy / derivation
- coordination state
- bounded execution layer
- Codex worker control
- runtime loop control and self-improvement control
- repository access to canonical persistence

### `services/ari-api`

Default contract into canonical ARI capabilities.

Exposes:

- memory
- tasks
- notes
- awareness and policy surfaces
- coordination and orchestration state
- execution and coding-action endpoints

### `services/ari-hub`

Primary web interface surface.

Owns:

- session UX
- rendering
- interaction flow
- calm state visibility
- API-backed client behavior

It must not become a second brain.

## Packages

`packages/` is no longer the main architecture center of gravity.

If logic belongs to the canonical brain, prefer placing it in `services/ari-core` unless there is a clear cross-service packaging reason.
