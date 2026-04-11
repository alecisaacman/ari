# Repository Structure

## Principle

This repository is organized around a clear separation between shared packages, runnable services, and architecture docs.

## Top Level

- `README.md`: project overview and startup path
- `AGENTS.md`: future-agent execution rules for this repository
- `docs/`: architecture source of truth
- `services/`: runnable service surfaces
- `packages/`: shared implementation modules
- `tests/`: verification
- `compose.yaml`: local infrastructure baseline
- `pyproject.toml`: Python tooling baseline

## Services

### `services/ari-core`

Background routines, orchestration, drift checks, and alert generation.

### `services/ari-api`

API surface for canonical read models and explainability queries. The first slice is a narrow read-only orchestration history surface.

### `services/ari-hub`

Primary web UI surface hosted on the home machine.

## Packages

### `packages/ari-state`

Canonical typed models and enums shared across the system.

### `packages/ari-memory`

Database wiring, migrations integration, persistence entities, and repositories.

### `packages/ari-events`

Canonical event schema, input normalization, and initial classification logic.

### `packages/ari-routines`

Daily check and other scheduled routine logic.

### `packages/ari-signals`

Signal and alert evaluation logic.

### `packages/ari-cli`

Operator terminal entrypoints and commands.
