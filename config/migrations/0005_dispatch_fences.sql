create table if not exists ari_execution_dispatch_fences (
    fence_id text primary key,
    execution_id text not null unique references ari_execution_action_executions(execution_id),
    task_id text not null references ari_execution_tasks(task_id),
    action_id text not null,
    idempotency_key text not null,
    attempt_id text not null references ari_execution_attempts(attempt_id),
    generation integer not null,
    lock_key text not null,
    state text not null,
    issued_at text not null,
    crossing_at text,
    returned_at text,
    revoked_at text,
    quiesced_at text,
    outcome_json text,
    terminal_by text,
    terminal_reason text,
    unique(task_id, action_id, generation)
);

create index if not exists idx_execution_dispatch_fences_action
    on ari_execution_dispatch_fences(task_id, action_id, state);

alter table ari_execution_effect_reconciliations add column dispatch_fence_state text;
