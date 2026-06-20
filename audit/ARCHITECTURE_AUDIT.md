# ARI/ACE Architecture Audit

Audit date: 2026-06-17

---

## System Overview

ARI/ACE currently exists as three separate technical systems with no integration:

| System | Location | Database | LLM | Status |
|---|---|---|---|---|
| ARI Spine | `~/Code/ari` | Postgres | None | Infrastructure built, zero data |
| ACE Command Center | `~/Code/openai-dev-sandbox` | SQLite | OpenAI GPT-4 | Running, real data |
| Networking CRM | `~/ARI(codex)/projects/networking-crm` | SQLite | None | Functional, isolated |

---

## ARI Spine Architecture

### Data Flow

```
User input
    ↓
[CLI: ari state set-daily] or [Hub: POST /actions/daily-state]
    ↓
[ari-api: PUT /daily-states/current]
    ↓
[ari-memory: DailyStateRepository.upsert()]
    ↓
[PostgreSQL: daily_states table]

                    ↓ (triggered manually — no scheduler exists)

[ari-core: run_signal_orchestration(session, input)]
    → DailyStateRepository.get(state_date)
    → WeeklyStateRepository.get(week_start)
    → OpenLoopRepository.list_open()
    → generate_signals(daily, weekly, open_loops)  [ari-signals]
    → persist signals (SHA-256 fingerprint dedup)
    → generate_alerts(signals)                     [ari-signals]
    → persist alerts (SHA-256 fingerprint dedup)
    → run_controller_cycle(decision) if supplied   [ari-core]
    → persist OrchestrationRun
    → persist ControllerEvents
    ↓
[ari-api: GET /orchestration-runs/latest]
    ↓
[ari-hub: GET /] → server-rendered HTML page
```

### Signal Engine (What ARI Currently Detects)

| Signal | Trigger | Severity |
|---|---|---|
| `open_loop_accumulation` | ≥7 open loops | WARNING; CRITICAL at ≥12 |
| `weekly_trajectory_drift` | No token overlap between weekly outcomes and daily priorities | WARNING |
| `elevated_stress` | Stress ≥8/10 | WARNING; CRITICAL at ≥9 |

All signals include structured evidence payloads so surfaces can explain why something was surfaced.

### Controller/Execution System

The spine has a governed execution framework:

```
ControllerDecision
    → evaluate_decision_authority()
        Rules: confidence threshold, action count limit, requires_approval flag,
               command allowlist, repo boundary check
        Outcomes: allow | require_approval | deny | defer
    ↓ (if allow)
    → ActionPlan (bounded list of ActionIntents)
    → execute_intent() for each intent
    → evaluate_observations()
    → VerificationResult
    → ControllerTrajectory (persisted to DB)
```

**Critical finding:** The executor (`executor.py`) currently supports only two real actions:
- `READ_FILE` — reads a file within the repo boundary
- `RUN_COMMAND` — runs one of exactly two allowed commands: `pytest -q` or `pytest tests/unit -q`

The governance framework is complete. The governed actions are only self-tests. This is intentional scaffolding but the executor must be expanded before ARI can automate anything real.

### Persistence Model

| Entity | Table | Key Behavior |
|---|---|---|
| DailyState | `daily_states` | One per day, upsert |
| WeeklyState | `weekly_states` | One per week_start, upsert |
| OpenLoop | `open_loops` | UUID PK, status: open/closed |
| Project | `projects` | UUID PK, slug |
| Signal | `signals` | UUID PK + SHA-256 fingerprint (idempotent) |
| Alert | `alerts` | UUID PK + SHA-256 fingerprint (idempotent) |
| OrchestrationRun | `orchestration_runs` | UUID PK, links to signals/alerts |
| ControllerEvent | `controller_events` | Ordered event stream per run |
| PendingApproval | `pending_approvals` | Status: pending/approved/denied |

Fingerprint-based deduplication means re-running orchestration for the same state_date and same input state produces the same signals/alerts without duplication. This is correct and valuable.

### Migrations (5 versions, all applied)

1. `20260410_0001` — Initial schema (daily_states, weekly_states, open_loops, projects, events, signals, alerts)
2. `20260410_0002` — Orchestration run history
3. `20260422_0003` — Controller trajectory fields on orchestration_runs
4. `20260422_0004` — Controller event stream table
5. `20260422_0005` — Pending approvals table

Schema is coherent and migration discipline is good.

---

## ACE Command Center Architecture

### Data Flow

```
Job boards (USAJobs, RemoteOK, Remotive)
    ↓
[career_scout.py] → raw JSON in remote_cashflow_raw/
    ↓
[career_command_center: importers.py] → SQLite: remote_cashflow.sqlite
    ↓
[scoring.py] → opportunity scores
[routing.py] → BALANCED / AGGRESSIVE / CONSERVATIVE operating modes
[daily_actions.py] → prioritized daily action queue (top N)
    ↓
[ari_agent_hub: adapters/career_command.py] → maps daily actions → agent tasks
[ari_agent_hub: store.py] → SQLite: ari_agent_hub.sqlite
    ↓
[apps/ace_command_center/backend] FastAPI
    ↓
[apps/ace-command-center/frontend] React/Vite
```

### Agent Registry

22 agents seeded in `ari_agent_hub.seed`. Domains:
- `career.*` — job verification, packet builder, outreach, follow-up, scout
- `personal_ops.*` — task manager, scheduler, reminder
- `finance.*` — cashflow tracking, expense review
- `health.*` — movement check, stress review
- `networking.*` — contact researcher, outreach manager
- `knowledge.*` — research assistant, summarizer
- `content.*` — draft writer, content reviewer

The agent registry is well-designed as a catalog. None of these agents have real LLM execution wired in — they're registered personas, not running processes.

### Naming Inconsistency (Structural Risk)

There are two parallel ACE backends:
- `apps/ace_command_center/` (Python, snake_case) — the canonical FastAPI backend
- `apps/ace-command-center/` (TypeScript/React, kebab-case) — the canonical frontend

These look like two separate projects but are actually the frontend and backend of the same app. The naming inconsistency (kebab vs snake) creates confusion. The backend README is empty. The frontend connects to the backend API at `localhost:8000`.

---

## Networking CRM Architecture

```
networking-crm/
    src/networking_crm/
        db.py         → SQLite: runtime/state/networking.db
        ari.py        → ARI integration hooks (currently stubbed)
        clip.py       → Screen clip capture
        content.py    → Content generation
        frame.py      → Visual frame composition
        record.py     → Recording management
        storyboard.py → Storyboard builder
        video.py      → Video output
        suits/        → Style/layout definitions
```

This is more than a CRM — it contains a full content creation pipeline. `ari.py` suggests intentional integration hooks into ARI were planned. The contact CRM schema is in `config/schema.sql`.

---

## Quality Ratings

### Code Organization
- **ARI Spine: Good** — Clear packages vs services split. Each package has one responsibility. Monorepo configured correctly.
- **ACE Command Center: Needs Work** — Business logic (career_command_center), registry (ari_agent_hub), backend (apps/ace_command_center), and frontend (apps/ace-command-center) are peers at the same level with inconsistent naming conventions.

### Type Safety and Maintainability
- **ARI Spine: Good** — Pydantic v2 with `extra="forbid"` on all models. mypy strict=True configured. `from __future__ import annotations` throughout.
- **ACE Command Center: Needs Work** — Python is largely untyped. No mypy configuration found.

### Error Handling
- **ARI Spine: Good** — Hub catches `HubAPIError` at every call site with graceful fallback rendering. Form parsing validates all fields. API returns structured error responses.
- **ACE Command Center: Needs Work** — No consistent error handling pattern. Root-level test files handle errors differently from module tests.

### Security
- **ARI Spine: Good** — All HTML uses `html.escape()` throughout the 1,295-line hub template. No SQL injection risk (SQLAlchemy ORM). Local-only, no auth needed.
- **ACE Command Center: Needs Work** — FastAPI backend has no authentication. Documented as local-only (`127.0.0.1`) but not enforced. Input from job scrapers treated as untrusted display data (documented in manifest — correct).
- **Both: Flag** — `.env` files with real credentials exist in both repos. Both are gitignored. Do not change this.

### Test Coverage
- **ARI Spine: Good** — 14 test files, ~162 tests, 3,747 lines of test code. Covers models, events, signals, orchestration, history, controller typed execution, approval workflow, API endpoints, hub rendering, CLI state, CLI history, CLI approvals. Tests use in-memory SQLite (no Postgres required for test runs).
- **ACE Command Center: Needs Work** — Tests exist but coverage is unclear. Mix of root-level test scripts and `tests/` directory. Several root-level files named `test_*.py` appear to be one-off validation scripts rather than pytest suites.

### Logging and Observability
- **Both: Missing** — No structured logging. No metrics. No runtime observability. Signals and alerts are persisted (which provides some audit trail) but nothing monitors process health.

### Deployment Readiness
- **ARI Spine: Needs Work** — `compose.yaml` only starts Postgres. No way to start ari-api, ari-core, or ari-hub via compose. No Makefile. No process supervisor.
- **ACE Command Center: Needs Work** — Shell scripts exist for starting backend and frontend but require separate terminals. No compose. Frontend requires `npm run dev` or serving the pre-built `dist/`.

### Local Development Experience
- **ARI Spine: Needs Work** — Requires: Docker (Postgres), Python 3.12, venv creation, `pip install -e ".[dev]"`, `alembic upgrade head`, then three separate terminals (ari-api, ari-hub, and optionally ari CLI). No single-command start.
- **ACE Command Center: Needs Work** — Requires: Python venv, `pip install`, and then either the Streamlit dashboards or the React frontend + Python backend (two terminals). Scripts help but aren't discoverable.

---

## Dependency Map

### ARI Spine Dependencies (pyproject.toml)
| Package | Version | Purpose |
|---|---|---|
| alembic | ≥1.15.0 | DB migrations |
| fastapi | ≥0.115.0 | API + hub web framework |
| psycopg[binary] | ≥3.2.0 | Postgres driver |
| pydantic | ≥2.9.0 | Canonical data models |
| pydantic-settings | ≥2.6.1 | Config from env |
| python-dotenv | ≥1.0.1 | .env loading |
| sqlalchemy | ≥2.0.36 | ORM + repository layer |
| typing-extensions | ≥4.12.2 | Type hints backport |

No external API dependencies. No LLM SDK. ARI spine makes zero network calls.

### ACE Command Center Dependencies (not pinned in pyproject.toml)
- `openai` — LLM calls for job evaluation, outreach drafting, scouting
- `streamlit` — Diagnostic dashboards
- `fastapi`, `uvicorn` — Backend API
- `react`, `vite`, `typescript` — Frontend
- SQLite (stdlib) — Persistence

Python version not pinned. This is a risk — the career tools were tested on whatever Python was installed.

---

## What the Spine Cannot Currently Do

These are gaps that need to be filled before ARI is useful:

1. **Cannot run automatically** — No scheduler, cron, or daemon. Orchestration runs only when manually triggered.
2. **Cannot notify you** — Alerts are generated and persisted but never delivered anywhere.
3. **Cannot make LLM calls** — No AI integration. Signal detection is rule-based only.
4. **Cannot take real external actions** — Executor is limited to running tests and reading its own files.
5. **Cannot ingest events from other systems** — No connectors to calendar, email, career tools, health data.
6. **Has no data** — As of the audit date, the Postgres database is empty or near-empty.
