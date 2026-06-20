# ARI/ACE Repository Map

Audit date: 2026-06-17

---

## Location Verdict

| Path | Status | Role |
|---|---|---|
| `~/Code/ari` | **PRIMARY — canonical** | ARI brain/spine. Git repo, Python 3.12, Postgres, FastAPI, Pydantic. This is the source of truth. |
| `~/Code/openai-dev-sandbox` | **ACTIVE SECONDARY** | Career domain + ACE Command Center. Git repo, Python + React/TS, OpenAI API, SQLite. Real data, real outputs. Slated for absorption into ARI. |
| `~/ARI (codex)` | **ACTIVE FRAGMENT** | ARI self-documentation layer (clips, frames, demos) + domain module prototypes (networking-crm). No top-level git. Should be formalized as a module area. |
| `~/ARI` | **DUPLICATE — archive** | Near-identical to `~/ARI (codex)` but older and missing `docs/`. No `docs/`, no `pet-runs`, no `.playwright-cli`. Same inodes as `~/Code/ari` on macOS case-insensitive FS — do NOT delete without checking. Archive this one. |
| `~/.codex` | **CONFIG** | Codex agent global state: `AGENTS.md` (good), memories, session history. Not project code. |
| `~/Desktop/ari_*.txt` | **EPHEMERAL** | A checkpoint note and a one-liner note. Not meaningful. Can be cleared. |

---

## Primary Spine: `~/Code/ari`

```
ari/
├── .env                          # Postgres credentials — SENSITIVE, never commit
├── .env.example                  # Safe template for new installs
├── .gitignore
├── AGENTS.md                     # Codex/agent instructions for this repo
├── README.md                     # Quick start + layout overview
├── alembic.ini                   # Migration config
├── compose.yaml                  # Docker Compose: Postgres only
├── pyproject.toml                # Python 3.12, setuptools monorepo config
│
├── docs/                         # Architecture source of truth
│   ├── charter.md                # Identity, purpose, product principles
│   ├── topology.md               # Services, surfaces, process layout
│   ├── hub-spec.md               # Hub UI requirements and design direction
│   ├── state-schema.md           # Full canonical state/model specification
│   ├── milestone-1-task-list.md  # Sprint 1–3 task breakdown
│   ├── mvp-build-order.md        # Sequence rationale
│   ├── deployment-plan.md        # Deployment strategy
│   └── repo-structure.md        # Repository layout guide
│
├── packages/                     # Shared library packages (no service dependencies)
│   ├── ari-state/                # Canonical Pydantic v2 models (14 classes)
│   │   └── src/ari_state/
│   │       ├── models.py         # DailyState, WeeklyState, OpenLoop, Project,
│   │       │                     # Signal, Alert, Event, OrchestrationRun,
│   │       │                     # ControllerDecision, ControllerTrajectory,
│   │       │                     # PendingApproval, ControllerEvent, etc.
│   │       └── enums.py          # All status/type enumerations
│   │
│   ├── ari-memory/               # SQLAlchemy 2.0 ORM + repository pattern
│   │   └── src/ari_memory/
│   │       ├── tables.py         # DB table definitions
│   │       ├── repositories.py   # DailyStateRepository, SignalRepository, etc.
│   │       ├── session.py        # SQLAlchemy session factory
│   │       └── config.py        # DB connection config via pydantic-settings
│   │
│   ├── ari-events/               # Event normalization and classification
│   │   └── src/ari_events/
│   │       ├── types.py          # Event type definitions
│   │       ├── normalizer.py     # Raw input → Event normalization
│   │       └── classifier.py    # Event classification logic
│   │
│   ├── ari-routines/             # Routine contracts (stub — not yet implemented)
│   │   └── src/ari_routines/
│   │       └── contracts.py     # Routine interface definitions
│   │
│   ├── ari-signals/              # Signal + alert generation engine
│   │   └── src/ari_signals/
│   │       └── engine.py         # generate_signals(), generate_alerts()
│   │                             # Detects: open_loop_accumulation,
│   │                             #          weekly_trajectory_drift,
│   │                             #          elevated_stress
│   │
│   └── ari-cli/                  # Terminal operator surface
│       └── src/ari_cli/
│           ├── main.py           # CLI entry point (Typer)
│           ├── state_cli.py      # Daily/weekly state read+write commands
│           ├── history_cli.py    # Orchestration history read commands
│           └── approval_cli.py  # Pending approval list + approve/deny
│
├── services/                     # Deployable services (depend on packages)
│   ├── ari-core/                 # Background orchestration engine
│   │   └── src/ari_core/
│   │       ├── orchestration.py  # run_signal_orchestration() — main entry point
│   │       ├── controller.py     # run_controller_cycle() — governed execution
│   │       ├── authority.py      # evaluate_decision_authority() — rule-based gates
│   │       ├── executor.py       # execute_intent() — STUBBED: only runs pytest/reads files
│   │       ├── evaluator.py      # Observation evaluation
│   │       ├── approvals.py      # Approval workflow logic
│   │       ├── controller_events.py  # ControllerEvent stream builder
│   │       ├── controller_state.py   # Cycle state machine
│   │       ├── decision_translate.py # Decision translation helpers
│   │       ├── execution_types.py    # ActionIntent, ExecutionObservation types
│   │       ├── history.py            # Orchestration history queries
│   │       ├── state.py              # State loading helpers
│   │       └── worker_client.py     # Worker client interface
│   │
│   ├── ari-api/                  # REST API over canonical state
│   │   └── src/ari_api/
│   │       ├── app.py            # FastAPI app factory + all route handlers
│   │       ├── main.py           # Uvicorn entry point
│   │       └── schemas.py       # Request/response Pydantic schemas
│   │
│   └── ari-hub/                  # HTML hub web surface
│       └── src/ari_hub/
│           ├── app.py            # FastAPI app + server-rendered HTML (1,295 lines)
│           └── main.py          # Uvicorn entry point
│
├── migrations/                   # Alembic migration versions
│   ├── env.py
│   ├── versions/
│   │   ├── 20260410_0001_initial_schema.py
│   │   ├── 20260410_0002_orchestration_run_history.py
│   │   ├── 20260422_0003_controller_trajectory.py
│   │   ├── 20260422_0004_controller_event_stream.py
│   │   └── 20260422_0005_approval_workflow.py
│   └── script.py.mako
│
└── tests/
    └── unit/                     # 14 test files, ~162 tests
        ├── test_models.py
        ├── test_events.py
        ├── test_signals.py
        ├── test_routines.py
        ├── test_memory.py
        ├── test_orchestration.py
        ├── test_orchestration_history.py
        ├── test_ari_core_typed_execution.py
        ├── test_approval_workflow.py
        ├── test_api_orchestration_history.py
        ├── test_hub_history_page.py
        ├── test_cli_state.py
        ├── test_cli_history.py
        └── test_cli_approvals.py
```

---

## Active Secondary: `~/Code/openai-dev-sandbox`

```
openai-dev-sandbox/
├── .env                          # OpenAI API key — SENSITIVE, never commit
├── context/                      # Static user context documents
│   ├── master_cv.md
│   ├── resume_baseline.md
│   ├── career_preferences.md
│   ├── target_roles.md
│   ├── strategic_positioning.md
│   ├── outreach_style.md
│   └── user_profile.json
│
├── career_command_center/        # Core career domain logic
│   ├── models.py                 # Opportunity, DailyAction, etc.
│   ├── db.py                     # SQLite access layer
│   ├── scoring.py                # Opportunity scoring
│   ├── routing.py                # Action routing (BALANCED/AGGRESSIVE modes)
│   ├── daily_actions.py          # Daily action generation
│   ├── dashboard_data.py         # Read-only dashboard data
│   ├── importers.py              # Job source importers
│   ├── packets.py                # Application packet generation
│   ├── reports.py                # Reporting
│   └── cli.py                   # CLI entry point
│
├── ari_agent_hub/                # Agent registry + task queue
│   ├── models.py                 # Agent, Task, Approval models
│   ├── store.py                  # AgentHubStore (SQLite-backed)
│   ├── seed.py                   # Seeds 22 agents + Telegram placeholder commands
│   ├── dashboard_data.py
│   ├── cli.py
│   └── adapters/
│       └── career_command.py    # Maps career daily actions → agent hub tasks
│
├── apps/
│   ├── ace_command_center/       # Python FastAPI backend (snake_case — CANONICAL)
│   │   └── backend/
│   │       ├── main.py
│   │       ├── routers/          # agents, approvals, career, health, outputs,
│   │       │                     # summary, system, tasks
│   │       └── services/         # agent_hub_service, career_command_service,
│   │                             # system_audit_service
│   │
│   └── ace-command-center/       # React/Vite frontend (kebab-case — ALSO CANONICAL?)
│       └── frontend/src/
│           ├── App.tsx
│           ├── api.ts
│           ├── components/       # AgentCard, ApprovalCard, CommandQueue,
│           │                     # MetricCard, StatusBadge, TaskCard, TaskDetailDrawer
│           └── pages/            # Agents, Approvals, CareerCommand, Outputs,
│                                 # SystemAudit, Tasks, Today
│
├── tools/                        # CLI tools (used by scripts/)
│   ├── scout_report_to_jobs.py
│   ├── batch_evaluate_jobs.py
│   ├── batch_draft_outreach.py
│   ├── save_opportunity.py
│   ├── update_status.py
│   ├── view_tracker.py
│   ├── review_pending_actions.py
│   ├── create_pending_action.py
│   └── context_loader.py
│
├── data/                         # Live operational data
│   ├── ari_agent_hub.sqlite      # Agent Hub DB
│   ├── remote_cashflow.sqlite    # Career Command + Remote Cashflow DB
│   └── career_tracker.csv        # Legacy CSV tracker
│
├── reports/, career_command_center_reports/,
│   career_command_center_packets/, remote_cashflow_reports/,
│   pending_remote_actions/, approved_actions/, application_prep/
│                                 # Generated artifacts — DO NOT DELETE
│
├── scripts/                      # Shell runners
│   ├── run_ace_command_center.sh
│   ├── run_ace_command_center_backend.sh
│   ├── run_ace_command_center_frontend.sh
│   ├── run_pipeline.sh
│   ├── run_scout.sh
│   └── run_dashboard.sh
│
└── tests/                        # pytest tests
    ├── test_career_command_center.py
    ├── test_agent_hub.py
    ├── test_ace_command_center.py
    └── test_remote_cashflow_*.py  (5 files)
```

---

## Active Fragment: `~/ARI (codex)`

```
ARI (codex)/
├── AGENTS.md                     # Codex agent instructions for this workspace
├── ai_empire/                    # Early AI router prototype (January 2026, Python 3.9)
│   ├── scripts/
│   │   ├── router_v0.py          # Input → prompt dispatch router
│   │   └── router_v1.py
│   ├── prompts/                  # meeting_to_actions, idea_screener, scope_cutter, etc.
│   ├── inputs/, outputs/, logs/  # Test runs from Jan 2026
│   └── .venv/                    # Python 3.9 standalone venv — ISOLATED
│
├── projects/
│   ├── networking-crm/           # Functional contact/relationship CRM
│   │   ├── src/networking_crm/   # ari.py, clip.py, content.py, db.py, frame.py,
│   │   │                         # record.py, storyboard.py, video.py, suits/
│   │   ├── config/schema.sql
│   │   ├── prompts/system.md
│   │   └── runtime/state/networking.db
│   │
│   └── _sandbox/                 # Empty template skeleton (git repo)
│
├── clips/2026-04-08/             # ARI self-documentation: screen recordings + text logs
├── frames/2026-04-08/            # ARI framed terminal/browser recordings
├── demos/2026-04-08/             # ARI demo outputs (priority clips, live demos)
├── content/                      # Content drafts
├── storyboards/                  # Visual storyboard planning
├── sessions/, recordings/        # Session logs
├── modules/networking-crm/state/ # DB mirror of networking state
│
└── docs/                         # Conceptual docs for ARI(codex) workspace
    ├── ari-vs-ace.md             # ARI/ACE identity and architecture split
    ├── current-state.md          # Integration risk assessment (key document)
    └── next-slice.md            # Next planned work
```

---

## Duplicate: `~/ARI`

Structurally identical to `~/ARI (codex)` but:
- Missing `docs/` folder
- Missing `pet-runs/` folder
- Missing `.playwright-cli/` folder
- Older modification dates throughout

**Action:** Archive this. Do not delete until `~/ARI (codex)` content is confirmed complete.

---

## Global Config: `~/.codex`

```
.codex/
├── AGENTS.md                     # Global Codex agent operating instructions (good quality)
├── memories/
│   ├── MEMORY.md                 # Memory index
│   └── memory_summary.md        # Summarized session context
├── goals_1.sqlite                # Codex goals DB
├── logs_2.sqlite                 # Codex session logs
├── state_5.sqlite                # Codex state DB
├── sessions/                     # Session transcripts
└── history.jsonl                # Interaction history
```
