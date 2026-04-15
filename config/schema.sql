create table if not exists contacts (
    id integer primary key,
    full_name text not null,
    company text,
    role_title text,
    location text,
    source text,
    email text,
    linkedin_url text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists notes (
    id integer primary key,
    contact_id integer not null,
    body text not null,
    created_at text not null default current_timestamp,
    foreign key (contact_id) references contacts (id) on delete cascade
);

create table if not exists follow_ups (
    id integer primary key,
    contact_id integer not null,
    due_on text not null,
    status text not null default 'pending',
    reason text,
    created_at text not null default current_timestamp,
    completed_at text,
    foreign key (contact_id) references contacts (id) on delete cascade
);

create table if not exists ari_notes (
    id integer primary key,
    title text not null,
    body text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists ari_tasks (
    id integer primary key,
    title text not null,
    status text not null default 'open',
    notes text not null default '',
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists ari_memories (
    id integer primary key,
    type text not null,
    title text not null,
    content text not null,
    tags_json text not null default '[]',
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(type, title)
);

create table if not exists ari_projects (
    id text primary key,
    title text not null,
    goal text not null,
    completion_criteria text not null,
    status text not null,
    source text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_project_milestones (
    id text primary key,
    project_id text not null,
    title text not null,
    status text not null,
    completion_criteria text not null,
    sequence integer not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_project_steps (
    id text primary key,
    project_id text not null,
    milestone_id text not null,
    title text not null,
    status text not null,
    completion_criteria text not null,
    depends_on_step_ids_json text not null,
    blocked_by_json text not null,
    sequence integer not null,
    linked_task_id text,
    linked_improvement_id text,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_orchestration_records (
    id text primary key,
    source text not null,
    raw_output text not null,
    status text not null,
    classification text,
    concise_summary text not null,
    next_instruction text not null,
    reasoning text not null,
    escalation_required integer not null,
    escalation_packet_json text not null,
    alec_decision text not null,
    parent_orchestration_id text,
    linked_improvement_ids_json text not null,
    verification_signal text,
    linkage_mode text not null,
    created_at text not null,
    processed_at text
);

create table if not exists ari_self_improvements (
    id text primary key,
    capability text not null,
    missing_capability text not null,
    why_it_matters text not null,
    what_it_unlocks text not null,
    smallest_slice text not null,
    next_best_action text not null,
    approval_required integer not null,
    relative_priority text not null,
    leverage_score integer not null,
    urgency_score integer not null,
    dependency_value_score integer not null,
    autonomy_impact_score integer not null,
    implementation_effort_score integer not null,
    priority_score integer not null,
    status text not null,
    dedupe_key text not null unique,
    approval_id text,
    task_id text,
    instruction_orchestration_id text,
    dispatch_record_id text,
    dispatch_orchestration_id text,
    dispatch_mode text,
    dispatch_evidence text,
    consumed_at text,
    consumer text,
    completion_orchestration_id text,
    completion_evidence text,
    verification_orchestration_id text,
    verification_evidence text,
    reflection_json text not null,
    first_observed_at text not null,
    last_observed_at text not null,
    approved_at text,
    queued_at text,
    dispatched_at text,
    completed_at text,
    verified_at text
);

create table if not exists ari_builder_dispatch_records (
    id text primary key,
    orchestration_id text not null,
    linked_improvement_ids_json text not null,
    mode text not null,
    instruction text not null,
    summary text not null,
    reasoning text not null,
    routing_state text not null,
    dispatch_status text not null,
    trigger text not null,
    dispatched_at text not null,
    consumed_at text,
    consumer text,
    completion_orchestration_id text,
    verification_orchestration_id text,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_execution_outcomes (
    item_key text primary key,
    item_type text not null,
    item_id text not null,
    title text not null,
    state text not null,
    stage text not null,
    state_since text not null,
    last_progress_at text not null,
    completed_at text,
    blocked_reason text,
    failure_reason text,
    verification_signal text,
    next_action text not null,
    evidence_mode text not null,
    metadata_json text not null,
    updated_at text not null
);

create table if not exists ari_coding_actions (
    id text primary key,
    title text not null,
    summary text not null,
    status text not null,
    approval_required integer not null,
    risky integer not null,
    target_paths_json text not null,
    operations_json text not null,
    verify_command text not null,
    working_directory text not null,
    current_step text not null,
    last_command_run_id text,
    last_command_summary text not null,
    result_summary text not null,
    retryable integer not null default 0,
    blocked_reason text,
    created_at text not null,
    approved_at text,
    applied_at text,
    tested_at text,
    passed_at text,
    failed_at text,
    verified_at text,
    updated_at text not null
);

create table if not exists ari_command_runs (
    id text primary key,
    action_id text not null,
    command text not null,
    cwd text not null,
    success integer not null,
    exit_code integer not null,
    timed_out integer not null,
    retryable integer not null,
    stdout text not null,
    stderr text not null,
    classification_json text not null,
    created_at text not null
);

create table if not exists ari_file_mutations (
    id text primary key,
    action_id text,
    path text not null,
    operation text not null,
    success integer not null,
    details text not null,
    previous_sha256 text,
    new_sha256 text,
    created_at text not null
);

create table if not exists ari_awareness_snapshots (
    id text primary key,
    mode text not null,
    summary text not null,
    current_focus_json text not null,
    tracking_json text not null,
    recent_intent_json text not null,
    signature text not null,
    created_at text not null
);
