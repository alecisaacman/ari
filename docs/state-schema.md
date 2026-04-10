# State Schema

## Canonical Principle

There is one canonical shared state model across all surfaces.

The canonical models are defined in `packages/ari-state` and persisted through `packages/ari-memory`. API, hub, CLI, notifications, and later voice should depend on those shared models instead of inventing local variants.

## Initial Canonical Models

### DailyState

Represents the active day-level operating frame for ARI.

Core fields:

- `date`
- `priorities` (top 1-3)
- `win_condition`
- `movement` (`true`/`false`/`null`)
- `stress` (`1..10` or `null`)
- `next_action`
- `last_check_at`

### WeeklyState

Represents the current week-level frame and review context.

Core fields:

- `week_start`
- `outcomes` (top 3)
- `cannot_drift`
- `blockers`
- `lesson`
- `last_review_at`

### OpenLoop

Represents an unresolved commitment, question, or active thread that should not be silently lost.

Core fields:

- `id`
- `title`
- `status`
- `kind`
- `priority`
- `source`
- `notes`
- `project_id`
- `opened_at`
- `due_at`
- `last_touched_at`

### Project

Represents a longer-lived area of execution containing related loops and events.

Core fields:

- `id`
- `slug`
- `name`
- `status`
- `summary`
- `tags`

### Signal

Represents an interpretable system observation derived from state or events.

Core fields:

- `id`
- `kind`
- `severity`
- `summary`
- `reason`
- `evidence`
- `related_entity_type`
- `related_entity_id`
- `detected_at`

### Event

Represents normalized system input or internal activity.

Core fields:

- `id`
- `source`
- `category`
- `occurred_at`
- `title`
- `body`
- `payload`
- `normalized_text`

Initial event categories:

- `daily_update`
- `weekly_planning`
- `weekly_reflection`
- `open_loop_add`
- `open_loop_update`
- `open_loop_resolve`
- `project_update`
- `signal_generated`
- `alert_generated`
- `capture`
- `intelligence_item`

### Alert

Represents a surfaced escalation created from one or more signals.

Core fields:

- `id`
- `status`
- `channel`
- `escalation_level`
- `title`
- `message`
- `reason`
- `source_signal_ids`
- `created_at`
- `sent_at`

### OrchestrationRun

Represents one durable execution of the narrow orchestration path for a target state date.

Core fields:

- `id`
- `state_date`
- `state_fingerprint`
- `executed_at`
- `signal_ids`
- `alert_ids`

## Explainability

Signals and alerts must preserve enough evidence to answer "why was this surfaced?" directly.

- Signals retain `reason` and structured `evidence`.
- Alerts retain `reason`, `source_signal_ids`, and `escalation_level`.
- Surfaces should expose this explanation path without inventing alternate local logic.

## Initial Orchestration Path

The first `ari-core` orchestration path remains intentionally narrow.

- accept execution inputs that identify the target state date and detection time
- load the relevant `DailyState`, `WeeklyState`, and open `OpenLoop` records from persistence
- run the canonical signal engine
- persist the generated `Signal` records before creating alerts
- generate `Alert` records from the persisted signals
- persist the generated `Alert` records without delivering notifications

This path must stay explainable end to end. `ari-core` orchestrates repository access and uses the canonical signal and alert models, but it must not add parallel signal or alert logic outside `packages/ari-signals`.

Repeated orchestration runs must also stay stable and explainable.

- persist a lightweight `OrchestrationRun` record for each execution
- use durable fingerprints on persisted `Signal` and `Alert` records to avoid recreating identical outputs for the same `state_date`
- preserve the original `reason`, `evidence`, and `source_signal_ids` chain when reusing prior records
- support a narrow read path that can load the latest run, the previous run, the linked signals and alerts for a run, and a direct comparison of the latest two runs for the same `state_date`

## Initial Routine Contracts

The first routine layer writes directly onto the canonical state model and emits matching canonical events.

### Daily Check

- writes `DailyState`
- fields updated: `priorities`, `win_condition`, `movement`, `stress`, `next_action`, `last_check_at`
- emits `EventCategory.DAILY_UPDATE`

### Weekly Planning

- writes `WeeklyState`
- fields updated: `outcomes`, `cannot_drift`, `blockers`, `last_review_at`
- preserves `lesson` unless a later weekly reflection changes it
- emits `EventCategory.WEEKLY_PLANNING`

### Weekly Reflection

- writes `WeeklyState`
- fields updated: `lesson`, optional `blockers`, `last_review_at`
- preserves the active week's `outcomes` and `cannot_drift`
- emits `EventCategory.WEEKLY_REFLECTION`

## Initial Signal Scope

The first signal layer remains intentionally narrow and explainable.

- `open_loop_accumulation`
- `weekly_trajectory_drift`
- `elevated_stress`

These signals are generated from canonical state and retain structured evidence payloads so later surfaces can explain them without re-deriving logic.

## Persistence Strategy

- Use Postgres as the durable store.
- Use migrations for schema evolution.
- Use repository classes for data access.
- Keep persistence entities aligned with canonical shared models.
- Persist `Signal` and `Alert` as first-class durable records, not transient outputs.
