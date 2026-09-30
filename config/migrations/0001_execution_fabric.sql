create table if not exists ari_execution_tasks (
    task_id text primary key,
    objective text not null,
    success_criteria_json text not null,
    requirements_json text not null,
    status text not null,
    current_plan_json text not null,
    plan_revision integer not null default 0,
    linked_project_id text,
    linked_task_id text,
    linked_milestone_id text,
    linked_goal_id text,
    authority_snapshot_ref text,
    authority_snapshot_hash text,
    latest_checkpoint_id text,
    result_id text,
    schema_version integer not null default 1,
    row_version integer not null default 1,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_execution_attempts (
    attempt_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    executor_id text not null,
    backend_id text not null,
    model_ref text,
    status text not null,
    continuation_checkpoint_id text,
    failure_json text,
    provenance_json text not null,
    started_at text not null,
    ended_at text
);

create table if not exists ari_execution_checkpoints (
    checkpoint_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    sequence integer not null,
    trigger text not null,
    objective text not null,
    success_criteria_json text not null,
    current_plan_json text not null,
    completed_steps_json text not null,
    pending_steps_json text not null,
    important_findings_json text not null,
    assumptions_json text not null,
    decisions_json text not null,
    artifacts_json text not null,
    actions_taken_json text not null,
    verification_results_json text not null,
    errors_json text not null,
    provider_json text not null,
    capacity_observations_json text not null,
    next_recommended_action text,
    authority_snapshot_ref text,
    authority_snapshot_hash text,
    parent_checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    payload_sha256 text not null,
    provenance_json text not null,
    created_at text not null,
    unique(task_id, sequence)
);

create table if not exists ari_execution_events (
    event_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    sequence integer not null,
    event_type text not null,
    causal_event_id text references ari_execution_events(event_id),
    idempotency_key text unique,
    payload_json text not null,
    provenance_json text not null,
    created_at text not null,
    unique(task_id, sequence)
);

create table if not exists ari_execution_results (
    result_id text primary key,
    task_id text not null unique references ari_execution_tasks(task_id),
    status text not null,
    objective text not null,
    outcome text not null,
    success_criteria_evaluation_json text not null,
    artifacts_json text not null,
    evidence_json text not null,
    verification_json text not null,
    unresolved_issues_json text not null,
    decisions_requiring_alec_json text not null,
    recommended_next_action text,
    provider_provenance_json text not null,
    execution_history_json text not null,
    final_checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    created_at text not null
);

create index if not exists idx_execution_attempts_task
    on ari_execution_attempts(task_id, started_at);
create index if not exists idx_execution_checkpoints_task
    on ari_execution_checkpoints(task_id, sequence);
create index if not exists idx_execution_events_task
    on ari_execution_events(task_id, sequence);
