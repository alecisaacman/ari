# State Schema

## Canonical Principle

There is one canonical shared state model across ARI.

The canonical source of truth lives in:

- `services/ari-core` for domain logic and persistence access
- `services/ari-api` for the default contract into that logic
- `config/schema.sql` for the durable SQLite schema

The hub, CLI, notifications, and later mobile surfaces must consume this canonical state instead of inventing local ownership.

## Durable Canonical Domains

### Notes

Canonical note storage lives in ARI and is surfaced through the API and hub.

Core fields:

- `id`
- `title`
- `body`
- `tags`
- `created_at`
- `updated_at`

### Tasks

Tasks are canonical ARI work items.

Core fields:

- `id`
- `title`
- `status`
- `priority`
- `details`
- `created_at`
- `updated_at`
- `completed_at`

### Structured Memory

Structured memory is canonical and brain-owned.

Current memory types include:

- `identity`
- `preference`
- `goal`
- `active_project`
- `priority`
- `routine`
- `operating_principle`
- `approval_decision`
- `working_state`
- `fact`

Core fields:

- `id`
- `memory_type`
- `title`
- `content`
- `tags`
- `created_at`
- `updated_at`

### Coordination State

Coordination state is canonical and includes the execution/planning spine that used to drift into ACE.

Current coordination records include:

- orchestration records
- self-improvements
- projects
- project milestones
- project steps
- builder dispatch records
- execution outcomes

These records support:

- orchestration history
- improvement lifecycle tracking
- project-level planning state
- dispatch truth
- execution truth

### Awareness Snapshots

ARI persists derived awareness snapshots canonically.

These snapshots summarize:

- current focus
- top blockers
- top improvement
- active project state
- recent reasoning context

They are derived from canonical state, not authored locally by the hub.

### Coding Actions

Bounded coding actions are now canonical operator records.

They are the first real execution layer for ARI’s coding loop.

Lifecycle stages:

- `proposed`
- `approved`
- `applied`
- `tested`
- `passed`
- `failed`
- `verified`

Supporting execution records:

- `ari_coding_actions`
- `ari_file_mutations`
- `ari_command_runs`
- `ari_execution_outcomes`
- `ari_runtime_execution_plan_previews`
- `ari_runtime_execution_runs`

Coding actions retain:

- changed files
- mutation history
- verification commands
- stdout / stderr
- exit code
- final outcome

Runtime execution runs retain:

- execution goal
- repo context snapshots
- worker decisions
- worker plans
- action results
- verification results
- retry / stop outcome

## Explainability

Canonical state must remain explainable.

ARI should always be able to answer:

- what changed
- why it changed
- what evidence exists
- what command ran
- what succeeded or failed
- whether a conclusion is proven or inferred

This applies especially to:

- orchestration decisions
- self-improvement lifecycle movement
- execution outcomes
- coding action verification

## Current Execution Model

The current operator layer is intentionally bounded.

ARI can now:

- read files inside the execution root
- write or patch approved files inside the execution root
- run allowlisted verification commands
- build bounded worker plans from explicit goals
- execute and verify multi-action plans
- persist command results and mutation history
- surface execution truth through the API and hub

ARI cannot yet:

- generate high-quality coding actions autonomously
- retry intelligently after failure
- run a full model-driven decision-and-repair loop
- control a live terminal session broadly

That remaining gap is the current product bottleneck.

## Persistence Strategy

- SQLite is the durable local store.
- `config/schema.sql` is the canonical schema source.
- `services/ari-core` owns repository and mutation logic.
- `services/ari-api` is the default service contract.
- `services/ari-hub` consumes canonical state and should not become a second brain.
