# Deployment Plan

## Target Environment

The home computer is the primary runtime environment for Milestone 1.

## Baseline Components

- Postgres via Docker Compose
- Python runtime for shared packages, routines, and services
- local web serving for the hub and API

## Deployment Phases

### Phase 1: Local Spine

- bring up Postgres
- run migrations
- validate repository layer
- validate routines against local state

### Phase 2: Local Surfaces

- expose the API
- expose the hub
- validate explainability paths end to end

### Phase 3: Notification Path

- add one notification channel
- ensure alerts are durable, idempotent, and explainable

## Operational Constraints

- prefer single-machine durability over distributed complexity
- keep local startup straightforward
- avoid infrastructure that is unnecessary for Milestone 1
