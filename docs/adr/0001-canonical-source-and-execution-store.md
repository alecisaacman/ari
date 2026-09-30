# ADR 0001: Canonical Source and Execution Store

- Status: Accepted
- Date: 2026-09-30

## Context

ARI must own task continuity even when an executing model, provider, process, or
session disappears. The repository currently contains several useful persistence
mechanisms, but their roles must be explicit before execution state expands.

## Decision

1. The source-bearing Git checkout is the canonical implementation of ARI. For
   this work, that checkout is
   `/Users/alecisaacman/CODING/ARI (codex)/projects/ari-canonical` on branch
   `feature/durable-execution-ledger`. A similarly named empty checkout is not a
   source of truth. Git history and repository documentation establish identity;
   the absolute local path is an operator fact, not a portable runtime dependency.
2. ARI's local SQLite database is the canonical durable store for Execution
   Fabric tasks, attempts, checkpoints, events, and results.
3. `config/schema.sql` remains the legacy baseline schema. Ordered,
   checksum-verified SQL files in `config/migrations/` are the canonical source
   for additive schema evolution.
4. Postgres-backed packages, Hub-local SQLite, and JSON status or snapshot files
   are not co-equal task truth. They may be adapters, read models, caches, or
   transport records only.
5. Filesystem queues and gateway event files are ingress and transport. Ingress
   must be normalized into ARI-owned state before it becomes execution truth.
6. ACE and every other surface must ultimately consume ARI-owned state through
   the ARI API or an explicitly derived read model. A surface may not independently
   decide task status, approval state, completion, or continuation.
7. Authority and approval context belongs to the task and checkpoint. Starting a
   later attempt does not widen or replace that authority.

## Consequences

- The current bounded `ExecutionController` remains the execution mechanism.
- The new execution ledger is additive and coexists with legacy runtime run and
  coding-action records while consumers migrate deliberately.
- A task has one stable `task_id`; each worker session is a distinct attempt.
- Checkpoints and events are immutable, ordered facts. The task row is a compact
  current-state pointer, and the result row is the normalized terminal contract.
- Provider selection and failover remain future work. This decision establishes
  the provider-neutral continuity boundary they will use.

## Not decided here

- Provider scoring or routing
- Automatic failover policy
- Claude, Codex, or local-model adapters
- Scheduler redesign
- Removal or migration of legacy execution records
