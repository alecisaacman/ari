create table if not exists ari_execution_effect_reconciliations (
    reconciliation_id text primary key,
    request_key text not null unique,
    execution_id text not null references ari_execution_action_executions(execution_id),
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    reserving_attempt_id text not null references ari_execution_attempts(attempt_id),
    decision_id text not null references ari_execution_resume_decisions(decision_id),
    action_id text not null,
    action_digest text not null,
    idempotency_key text not null,
    requested_outcome text not null,
    outcome text not null,
    previous_state text not null,
    effective_previous_state text not null,
    resulting_state text not null,
    retry_eligible integer not null,
    reconciled_by text not null,
    reason text not null,
    assessment text not null,
    evidence_json text not null,
    evidence_sha256 text not null,
    basis_checkpoint_id text not null references ari_execution_checkpoints(checkpoint_id),
    checkpoint_id text references ari_execution_checkpoints(checkpoint_id),
    provenance_json text not null,
    created_at text not null
);

create index if not exists idx_execution_effect_reconciliations_execution
    on ari_execution_effect_reconciliations(execution_id, created_at);
create index if not exists idx_execution_effect_reconciliations_task
    on ari_execution_effect_reconciliations(task_id, created_at);

alter table ari_execution_action_executions add column reconciliation_id text
    references ari_execution_effect_reconciliations(reconciliation_id);
