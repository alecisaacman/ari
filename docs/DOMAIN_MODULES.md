# Domain Modules

Reference map of every package and service in the monorepo: what it owns, its public interface, and how it connects to everything else.

---

## Packages

### `ari-state`
**Layer:** Shared types
**Owns:** All canonical data models and enumerations.
**Key modules:**
- `models.py` — Pydantic v2 models: `OpenLoop`, `Signal`, `Alert`, `OrchestrationRun`, `DailyState`, `WeeklyTrajectory`, `Event`, and their `Create*Input` forms
- `enums.py` — `OpenLoopStatus`, `OpenLoopPriority`, `OpenLoopKind`, `AlertEscalationLevel`, `AlertStatus`, `AlertChannel`, `SignalKind`, and others

**Depends on:** nothing internal
**Used by:** everything

---

### `ari-memory`
**Layer:** Persistence
**Owns:** Database connection, ORM table definitions, and all repository classes.
**Key modules:**
- `config.py` — `DatabaseSettings` (reads `DATABASE_URL`, defaults to `postgresql+psycopg://ari:ari@localhost:5432/ari`)
- `tables.py` — SQLAlchemy ORM rows: `OpenLoopRow`, `SignalRow`, `AlertRow`, `OrchestrationRunRow`, `EventRow`, `ControllerEventRow`, `PendingApprovalRow`
- `repositories.py` — `OpenLoopRepository`, `SignalRepository`, `AlertRepository`, `OrchestrationRunRepository`, `EventRepository`, `ControllerEventRepository`, `PendingApprovalRepository`
- `session.py` — `create_engine`, `create_session_factory`

**Depends on:** `ari-state`
**Used by:** `ari-core`, `ari-api`, `ari-hub`, scripts

---

### `ari-events`
**Layer:** Event ingestion
**Owns:** Raw event normalization and classification before they become canonical state.
**Key modules:**
- `types.py` — raw event type definitions
- `normalizer.py` — converts raw inputs to a normalized form
- `classifier.py` — labels events by kind/domain

**Depends on:** `ari-state`
**Used by:** `ari-core`

---

### `ari-routines`
**Layer:** Scheduled logic contracts
**Owns:** The abstract contract interface for routines (work units run on a schedule or trigger).
**Key modules:**
- `contracts.py` — `Routine` protocol / base class

**Depends on:** `ari-state`
**Used by:** `ari-core`

---

### `ari-signals`
**Layer:** Signal detection
**Owns:** The signal engine — reads daily state and emits typed signals and alerts.
**Key modules:**
- `engine.py` — `run_signal_engine(state)`, individual detector functions, `generate_alerts(signals)`. Currently detects: `open_loop_accumulation`, `weekly_trajectory_drift`, `elevated_stress`

**Signal → Alert mapping:**
| Signal | Default Escalation |
|--------|-------------------|
| `open_loop_accumulation` | `ELEVATED` |
| `weekly_trajectory_drift` | `ELEVATED` |
| `elevated_stress` | `INTERRUPTIVE` |

**Depends on:** `ari-state`
**Used by:** `ari-core`

---

### `ari-cli`
**Layer:** Operator surface (terminal)
**Owns:** The `ari` command-line tool.
**Key modules:**
- `main.py` — argument parser, entry point, routes to handlers
- `history_cli.py` — `ari orchestration run`, `ari orchestration latest`
- `state_cli.py` — `ari today read/write`, `ari week read/write`, `ari loops read/create/close`
- `approval_cli.py` — `ari approvals list`, `ari approvals approve/reject`

**CLI surface summary:**
```
ari today read|write --state-date YYYY-MM-DD
ari week read|write --state-date YYYY-MM-DD
ari loops read|create|close
ari orchestration run --state-date YYYY-MM-DD
ari orchestration latest --state-date YYYY-MM-DD
ari approvals list
ari approvals approve|reject --approval-id UUID
```

**Depends on:** `ari-state`, `ari-memory`, `ari-core`
**Used by:** humans, `daily-check.sh`

---

## Services

### `ari-core`
**Layer:** Domain logic
**Owns:** All business logic that reads/mutates canonical state: orchestration, signal evaluation, controller execution, state management, and history queries.
**Key modules:**
- `orchestration.py` — `run_signal_orchestration(session, RunSignalOrchestrationInput)` — main daily pipeline entry point
- `state.py` — `create_open_loop`, `close_open_loop`, `list_open_loops`, `create_daily_state`, `get_daily_state`, `create_weekly_trajectory`, `get_weekly_trajectory`
- `history.py` — `get_latest_run_details`, `get_previous_run_details`, `compare_latest_two_runs`, `get_signal_details`, `get_alert_details`
- `controller.py` — governed execution loop (decision → authority → plan → execute → verify)
- `authority.py` — checks whether a proposed action is within allowed scope
- `executor.py` — bounded execution: currently allows `pytest -q` and file reads within repo
- `evaluator.py` — run evaluator post-execution
- `approvals.py` — approval state transitions

**Depends on:** `ari-state`, `ari-memory`, `ari-events`, `ari-routines`, `ari-signals`
**Used by:** `ari-api`, `ari-hub`, `ari-cli`

---

### `ari-api`
**Layer:** HTTP service boundary
**Owns:** REST API for state reads and writes (consumed by `ari-hub` and external tooling).
**Key modules:**
- `app.py` — FastAPI application, all route handlers
- `schemas.py` — Pydantic request/response schemas
- `main.py` — ASGI entry point

**Runs on:** `127.0.0.1:8000`
**Current endpoints:** GET-only history and state reads; no orchestration trigger endpoint yet.

**Depends on:** `ari-state`, `ari-memory`, `ari-core`
**Used by:** `ari-hub`, future integrations

---

### `ari-hub`
**Layer:** Primary web surface
**Owns:** Server-rendered HTML dashboard showing current state, open loops, signals, alerts, and orchestration run history.
**Key modules:**
- `app.py` — FastAPI application (~1300 lines), all page routes and HTML templates
- `main.py` — ASGI entry point

**Runs on:** `127.0.0.1:8001`

**Depends on:** `ari-state`, `ari-memory`, `ari-core`
**Used by:** humans (browser)

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/start-ari.sh` | Start Postgres, run migrations, start ari-api + ari-hub, open browser |
| `scripts/stop-ari.sh` | Stop ari-api, ari-hub, and Postgres |
| `scripts/daily-check.sh` | Morning check: today state, open loops, orchestration run, notifications |
| `scripts/notify-alerts.py` | Send macOS notifications for unsent ELEVATED/INTERRUPTIVE alerts |
| `scripts/career-to-openloops.py` | Sync career opportunities from openai-dev-sandbox into ARI open loops |
| `scripts/com.ari.daily-orchestration.plist` | launchd agent: run daily-check.sh at 07:00 daily |

---

## Data Flow

```
Daily state (DailyState, WeeklyTrajectory)
        │
        ▼
ari-signals / engine.py
        │  detects patterns, emits Signal + Alert objects
        ▼
ari-core / orchestration.py
        │  persists signals + alerts (dedup by fingerprint), runs controller
        ▼
ari-memory / repositories.py
        │  writes to Postgres via SQLAlchemy
        ▼
ari-api / ari-hub
           read-only query layer, surfaces results to human
```

---

## Adding a New Domain

To add a new life domain (health, finance, relationships, etc.) to ARI's signal engine:

1. Add any new model fields to `ari-state/models.py` (e.g. `DailyState.sleep_score`)
2. Write an Alembic migration for the new columns
3. Add detector functions to `ari-signals/engine.py`
4. Add the new signal kind to `SignalKind` enum
5. Add `generate_alerts` mapping for the new signals
6. Write tests in `tests/`
