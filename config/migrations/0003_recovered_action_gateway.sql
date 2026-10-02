create table if not exists ari_execution_action_approvals (
    approval_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    checkpoint_id text not null references ari_execution_checkpoints(checkpoint_id),
    action_id text not null,
    action_digest text not null,
    target_resources_json text not null,
    authority_snapshot_ref text,
    authority_snapshot_hash text,
    status text not null,
    approved_by text not null,
    reason text not null,
    expires_at text,
    provenance_json text not null,
    created_at text not null,
    resolved_at text not null
);

create index if not exists idx_execution_action_approvals_lookup
    on ari_execution_action_approvals(task_id, action_digest, status, created_at);

create table if not exists ari_execution_resume_decisions (
    decision_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    checkpoint_id text not null references ari_execution_checkpoints(checkpoint_id),
    action_id text not null,
    proposed_action_json text not null,
    action_digest text not null,
    target_resources_json text not null,
    authority_snapshot_ref text,
    authority_snapshot_hash text,
    authority_scope_json text not null,
    approval_reference text,
    restrictions_json text not null,
    idempotency_key text not null,
    decision text not null,
    reason text not null,
    provenance_json text not null,
    created_at text not null
);

create index if not exists idx_execution_resume_decisions_task
    on ari_execution_resume_decisions(task_id, created_at);
create index if not exists idx_execution_resume_decisions_idempotency
    on ari_execution_resume_decisions(idempotency_key, created_at);

create table if not exists ari_execution_action_executions (
    execution_id text primary key,
    decision_id text not null references ari_execution_resume_decisions(decision_id),
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    action_id text not null,
    action_digest text not null,
    idempotency_key text not null unique,
    state text not null,
    effect_status text not null,
    pre_checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    result_checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    verification_checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    result_json text,
    verification_json text,
    evidence_json text not null,
    error_json text,
    started_at text,
    finished_at text,
    created_at text not null,
    updated_at text not null
);

create index if not exists idx_execution_action_executions_task
    on ari_execution_action_executions(task_id, created_at);
