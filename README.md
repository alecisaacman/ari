# ARI

ARI is the canonical source repository for the next implementation of the ARI system.

ARI is the outward identity. ACE is the internal ambient-presence doctrine that shapes how ARI behaves: one intelligence, many quiet processes, calm under normal conditions, immediately serious when stakes rise.

This repository starts docs-first and builds the system spine before surface polish.

## Milestone 1

Milestone 1 delivers a home-computer ARI that can:

- store canonical shared state
- run a daily check
- track open loops
- detect basic drift
- show the hub
- send one meaningful notification

## Architecture Summary

- The home computer hosts the ARI brain.
- Postgres is the durable system record for canonical state and events.
- Shared typed models are the source of truth across CLI, API, and hub.
- The hub is the primary visible surface, not the brain itself.
- Terminal, phone, notifications, and later voice are alternate surfaces into the same underlying orchestration layer.

## Repository Layout

- `docs/`: architecture and delivery source of truth
- `services/ari-core/`: background orchestration and routines
- `services/ari-api/`: API surface over canonical state and events
- `services/ari-hub/`: hub web surface
- `packages/ari-state/`: canonical typed state models
- `packages/ari-memory/`: persistence layer, repositories, database wiring
- `packages/ari-events/`: event schema, normalization, classification
- `packages/ari-routines/`: scheduled routines and behavioral flows
- `packages/ari-signals/`: signal and alert logic
- `packages/ari-cli/`: operator terminal surface
- `tests/`: unit and integration coverage

## Quick Start

1. Copy `.env.example` to `.env`.
2. Start Postgres with `docker compose up -d postgres`.
3. Use Python 3.12 to create a virtual environment and install dev dependencies.
4. Run migrations with `alembic upgrade head`.
5. Run tests with `pytest`.

## Runtime Baseline

- Intended repository baseline: Python 3.12
- Current code is kept conservative enough to read cleanly on older interpreters, but the canonical project target remains 3.12.

## CLI Read Surface

The first operator CLI surface is read-only orchestration history:

- `ari orchestration latest --state-date YYYY-MM-DD`
- `ari orchestration previous --state-date YYYY-MM-DD`
- `ari orchestration compare-latest-two --state-date YYYY-MM-DD`

These commands read canonical persisted orchestration history and show linked signals, alerts, reuse vs new outputs, and whether the state fingerprint changed.

## API Read Surface

The first `ari-api` surface is also narrow and read-only:

- `GET /orchestration-runs/latest?state_date=YYYY-MM-DD`
- `GET /orchestration-runs/previous?state_date=YYYY-MM-DD`
- `GET /orchestration-runs/compare-latest-two?state_date=YYYY-MM-DD`

These endpoints are a thin transport layer over canonical orchestration history queries and return structured explainability data for runs, linked signals, linked alerts, and reuse vs new output ids.

## Working Rules

- Treat `docs/` as the architecture source of truth.
- Keep one canonical shared state model.
- Avoid duplicating business logic across surfaces.
- Keep changes small, coherent, and reviewable.
- Update docs when architecture changes materially.
