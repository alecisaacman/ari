# ARI

ARI is a local-first agentic operating system for personal execution, work automation, and decision support.

The core idea is simple:

> One canonical intelligence, many surfaces.

ARI is the brain. ACE is the interface doctrine and surface layer. Codex and other agents may help build or operate parts of the system, but ARI remains the canonical source of state, policy, memory, and execution history.

## What ARI Is Building Toward

ARI is designed to help an operator maintain continuity across work, projects, decisions, routines, and open loops.

The system is not intended to be a loose collection of chatbots. It is being built as a durable local runtime that can:

- hold canonical state across days, weeks, projects, and open loops
- turn raw inputs into structured events
- derive explainable signals and alerts
- expose state through multiple surfaces without duplicating logic
- keep human approval boundaries around external actions
- produce artifacts that make work inspectable and reusable

## Current Status

ARI is an active prototype. The current repository focuses on the local execution spine:

- canonical Python core
- FastAPI service boundary
- Next.js hub surface
- typed state and event models
- local Postgres baseline
- explainable signal and alert paths
- testable routines and orchestration contracts

This is not yet a packaged public product. It is a working foundation for a serious local-first agentic system.

## Core Architecture

```text
operator
  |
  v
ACE surfaces: hub, terminal, phone, notifications, future companion UI
  |
  v
ari-api: service boundary over canonical capabilities
  |
  v
ari-core: routines, orchestration, signals, alerts, execution logic
  |
  v
canonical state + persistence
```

### Repository Layout

- `services/ari-core/` — canonical Python ARI runtime
- `services/ari-api/` — FastAPI wrapper over canonical ARI capabilities
- `services/ari-hub/` — Next.js ACE hub surface
- `docs/` — architecture and product direction
- `tests/` — Python verification for the converged repo
- `compose.yaml` — local Postgres baseline
- `pyproject.toml` — Python package and tooling configuration

## Product Doctrine

ARI follows a few strict design rules:

- ARI is the brain; ACE is the interface layer.
- Shared state is canonical.
- Surfaces should read from and write through ARI instead of inventing parallel logic.
- External actions require explicit approval unless a boundary has been deliberately expanded.
- Signals and alerts must be explainable after the fact.
- Local-first durability is preferred over premature cloud complexity.
- Build the spine before adding polish.

## Current Proof Module Direction

The first practical proof module is Career Command: a job-search and career-execution workflow that can scout roles, evaluate fit, draft outreach, track actions, and surface pending approvals.

The intended product loop is:

1. Scout opportunities.
2. Evaluate and rank fit.
3. Save selected targets.
4. Draft outreach or next actions locally.
5. Require human approval before any external send, application, or message.
6. Track the execution history.
7. Surface progress through ACE surfaces such as the hub and Telegram.

Career Command is not the whole product. It is the first concrete proof that ARI can turn messy work into a structured operating loop.

## Safety Boundaries

Current default boundary:

- no automatic applications
- no automatic emails
- no automatic LinkedIn messages
- no payment or purchasing actions
- no silent external side effects

ARI may draft, rank, summarize, track, and recommend. External actions should remain approval-gated.

## Quick Start

Create a Python 3.12 environment and install repo dependencies:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install '.[dev]'
```

Start local infrastructure:

```bash
cp .env.example .env
docker compose up -d
```

Install hub dependencies:

```bash
cd services/ari-hub
npm install
```

Run the API:

```bash
cd /path/to/ari
./.venv/bin/python -m uvicorn ari_api.main:app --host 127.0.0.1 --port 8000
```

Run the hub:

```bash
cd services/ari-hub
npm run dev
```

For LAN access:

```bash
npm run build
npm run start:lan
```

## Verification Baseline

```bash
./.venv/bin/python -m pytest tests/unit -q
```

```bash
cd services/ari-hub
node --import tsx --test --test-reporter spec tests/auth.test.ts tests/workspace.test.ts tests/orchestration-classifier.test.ts
npm run build
```

## Documentation Map

- `docs/charter.md` — identity, purpose, and product principles
- `docs/topology.md` — brain, API, hub, terminal, phone, and notifications
- `docs/state-schema.md` — canonical state, events, signals, alerts, and orchestration runs
- `docs/deployment-plan.md` — local-first deployment path
- `docs/mvp-build-order.md` — sequencing rationale
- `docs/product-narrative.md` — public-facing product story
- `docs/roadmap.md` — near-term execution direction

## Working Rule

Keep ARI canonical. Keep ACE thin. If a capability belongs to the brain, move it inward.
