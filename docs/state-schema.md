# State Schema

## Canonical Principle

There is one canonical shared state model across ARI.

The canonical source of truth lives in:

- `services/ari-core` for domain logic and persistence access
- `services/ari-api` for the default contract into that logic
- `config/schema.sql` for the legacy baseline SQLite schema
- `config/migrations/` for ordered, checksum-verified additive schema evolution

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

### Execution Fabric

The provider-neutral continuity ledger adds:

- `ari_execution_tasks` — stable objective, success criteria, requirements,
  authority references, current plan, status, and latest-checkpoint pointer
- `ari_execution_attempts` — each bounded worker session and its provenance
- `ari_execution_checkpoints` — append-only normalized recovery state
- `ari_execution_events` — append-only per-task ordered lifecycle facts
- `ari_execution_results` — one common terminal result contract per task
- `ari_execution_worker_heartbeats` — durable lease-renewal observations
- `ari_execution_continuation_packets` — canonical recovery input for one
  replacement attempt
- `ari_execution_continuation_acknowledgements` — replacement-worker evidence
  required before execution-ready state
- `ari_execution_action_approvals` — action-digest/resource-bound approvals
  that survive worker replacement without widening authority
- `ari_execution_resume_decisions` — ARI allow/deny/require-approval/block
  decisions for one recovered pending action
- `ari_execution_action_executions` — idempotency reservation, action result,
  effect certainty, verification evidence, checkpoint links, and the
  reconciliation that last resolved an uncertain effect
- `ari_execution_effect_reconciliations` — append-only, evidence-backed
  resolutions of uncertain or unverified external effects
- `ari_execution_dispatch_fences` — one per reserved execution: monotonic
  per-action generation, effect terminality (`in_process`/`unbounded`),
  issued/crossing/returned/lock_released/revoked lifecycle, the held lock's
  path/device/inode, the landing token once landing is ruled out, and the
  recorded dispatch outcome

Events and checkpoints use independent monotonic task sequences and are committed
together at each boundary. A checkpoint contains completed and pending steps,
findings, assumptions, decisions, artifacts, actions, verification, errors,
provider observations, next action, authority references, and provenance. Stored
payloads redact common secret fields and bound large output.

Migration `0002_execution_sessions` adds explicit task and attempt lifecycle
state, lease ownership/timestamps, prior/replacement attempt links, restrictions,
authority scope, approval state, continuation references, and recovery reasons.
See [Execution Session Recovery](execution/session-recovery.md).

Migration `0003_recovered_action_gateway` adds the durable approval, decision,
and idempotent execution records used by the one-action recovered execution
boundary. See [Recovered Action Authority Gateway](execution/recovered-action-gateway.md).

Migration `0004_effect_reconciliation` adds the reconciliation record and the
execution's `reconciliation_id` link. See
[Uncertain-Effect Reconciliation](execution/effect-reconciliation.md).

Migration `0005_dispatch_fences` adds dispatch fences and records the fence state
on each reconciliation. Per-action dispatch lock files live in `dispatch-locks/`
next to the canonical database path. See [Dispatch Safety Boundary](execution/dispatch-safety.md).

Migration `0006_redispatch_safety` renames fence state `quiesced` to
`lock_released`. It adds effect terminality, the held lock's identity, and the
landing token to fences. It replaces the reconciliation's `retry_eligible` with
`redispatch_safe` plus the bound `landing_token`, and resets every legacy record
to not safe. Legacy fences have no terminality and are treated as `unbounded`.

The legacy runtime execution records remain available during compatibility work;
they are not a second canonical task state.

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
- recover the latest durable task checkpoint after an interrupted worker process
- inspect a complete task bundle through `GET /execution/tasks/{task_id}`

ARI cannot yet:

- generate high-quality coding actions autonomously
- retry intelligently after failure
- run a full model-driven decision-and-repair loop
- control a live terminal session broadly
- route by provider capability or fail over automatically

That remaining gap is the current product bottleneck.

## Persistence Strategy

- SQLite is the durable local store.
- `config/schema.sql` plus immutable `config/migrations/*.sql` are the canonical
  schema sources.
- `initialize_database` applies them under explicit `BEGIN IMMEDIATE` transactions:
  each versioned migration's statements and its `ari_schema_migrations` row commit
  together or not at all, and which migrations are pending is decided only while
  holding SQLite's write lock, so concurrent initializers serialize instead of
  re-running the same migration. An initializer waits up to
  `ARI_SQLITE_LOCK_TIMEOUT_SECONDS` (default 30; must be finite, greater than 0 and
  at most 86400) for the write lock, then fails with `MigrationLockTimeout`.
- Migration script contract: statements are split with
  `sqlite3.complete_statement`; the final statement may omit its semicolon; a
  leading UTF-8 BOM is ignored; a script ending inside a string, quoted identifier
  or block comment is rejected. Transaction control (`BEGIN`, `COMMIT`, `END`,
  `ROLLBACK`, `SAVEPOINT`, `RELEASE`, `ROLLBACK TO`) is refused through SQLite's
  authorizer as each statement is prepared, so spelling, comments, BOMs or
  whitespace cannot disguise it; the same words inside strings, comments or quoted
  identifiers are harmless. `VACUUM` is refused by SQLite inside a transaction. Any
  rejection rolls the whole migration back unrecorded. Checksums remain SHA-256 of
  the file as read by `Path.read_text(encoding="utf-8")`.
- `services/ari-core` owns repository and mutation logic.
- `services/ari-api` is the default service contract.
- `services/ari-hub` consumes canonical state and should not become a second brain.
