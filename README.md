# ARI Canonical Repository

This repository now holds the real ARI system in canonical service form:

- `services/ari-core`: the canonical ARI brain
- `services/ari-api`: the transport layer over canonical ARI capabilities
- `services/ari-hub`: the ACE hub surface

ARI is the brain. ACE is the interface layer.

## What Lives Here Now

Canonical in `ari-core`:

- notes
- tasks
- structured memory
- policy and awareness derivation
- coordination state
- execution tracking
- project planning state

Surfaced in `ari-hub`:

- chat and hub UI
- approvals
- activity feed
- sessions and auth
- trigger and voice entrypoints
- workspace-scoped tools

## Repository Layout

- `services/ari-core/`: canonical Python ARI runtime
- `services/ari-api/`: FastAPI wrapper over canonical ARI core modules
- `services/ari-hub/`: Next.js ACE hub
- `config/schema.sql`: canonical SQLite schema used by `ari-core`
- `tests/`: canonical Python verification for the converged repo
- `docs/`: architecture and product direction

## Quick Start

1. Create a Python 3.12 environment and install repo dependencies:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install '.[dev]'
```

2. Install hub dependencies:

```bash
cd services/ari-hub
npm install
```

3. Run the canonical API:

```bash
cd /path/to/projects/ari-canonical
./.venv/bin/python -m uvicorn ari_api.main:app --host 127.0.0.1 --port 8000
```

4. Run the hub:

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

- Python 3.12
- `./.venv/bin/python -m pytest tests/unit -q`
- `cd services/ari-hub && node --import tsx --test --test-reporter spec tests/auth.test.ts tests/workspace.test.ts tests/orchestration-classifier.test.ts`
- `cd services/ari-hub && npm run build`

## Working Rule

Keep ARI canonical.
Keep ACE thin.
If a capability belongs to the brain, move it inward.
