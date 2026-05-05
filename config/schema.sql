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

create table if not exists ari_memory_blocks (
    id text primary key,
    layer text not null,
    kind text not null,
    title text not null,
    body text not null,
    source text not null,
    importance integer not null default 3,
    confidence real not null default 1.0,
    tags_json text not null default '[]',
    subject_ids_json text not null default '[]',
    evidence_json text not null default '[]',
    created_at text not null,
    updated_at text not null
);

create index if not exists idx_ari_memory_blocks_layer_updated
    on ari_memory_blocks (layer, updated_at desc);

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

create table if not exists ari_decision_records (
    id text primary key,
    orchestration_run_id text not null,
    signal_id text,
    intent text not null,
    decision_type text not null,
    priority integer not null,
    reasoning text not null,
    related_signal_ids_json text not null,
    related_entity_type text,
    related_entity_id text,
    proposed_action_json text not null,
    requires_approval integer not null,
    action_json text not null,
    confidence real not null,
    created_at text not null
);

create table if not exists ari_decision_dispatch_records (
    id text primary key,
    decision_id text not null,
    decision_reference text not null,
    status text not null,
    reason text not null,
    action_json text not null,
    execution_result_json text not null,
    created_at text not null
);

create table if not exists ari_decision_evaluation_records (
    id text primary key,
    decision_id text not null,
    dispatch_record_id text not null,
    decision_reference text not null,
    status text not null,
    reason text not null,
    next_step text not null,
    created_at text not null
);

create table if not exists ari_decision_cycle_records (
    id text primary key,
    orchestration_run_id text not null,
    status text not null,
    reason text not null,
    decision_count integer not null,
    dispatch_count integer not null,
    evaluation_count integer not null,
    created_at text not null
);

create table if not exists ari_runtime_loop_records (
    id text primary key,
    goal text not null,
    status text not null,
    reason text not null,
    cycles_run integer not null,
    max_cycles integer not null,
    final_output text not null,
    final_error text not null,
    last_worker_run_id text,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_runtime_worker_runs (
    id text primary key,
    loop_id text not null,
    cycle_index integer not null,
    prompt text not null,
    backend text not null,
    command_json text not null,
    cwd text not null,
    success integer not null,
    retryable integer not null,
    exit_code integer not null,
    stdout text not null,
    stderr text not null,
    created_at text not null
);

create table if not exists ari_runtime_controller_decisions (
    id text primary key,
    loop_id text not null,
    cycle_index integer not null,
    goal text not null,
    selected_slice_key text not null,
    selected_slice_title text not null,
    selected_slice_milestone text not null,
    selection_reason text not null,
    evidence_json text not null,
    verification_plan_json text not null,
    outcome_status text not null,
    outcome_reason text not null,
    next_control_action text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_runtime_action_plans (
    id text primary key,
    loop_id text not null,
    cycle_index integer not null,
    slice_key text not null,
    milestone text not null,
    attempt_kind text not null,
    task_description text not null,
    constraints_json text not null,
    likely_files_json text not null,
    expected_symbols_json text not null,
    verification_expectations_json text not null,
    retry_refinement_hints_json text not null,
    failed_checks_json text not null,
    prompt_text text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_runtime_execution_runs (
    id text primary key,
    goal_id text not null,
    objective text not null,
    status text not null,
    reason text not null,
    cycles_run integer not null,
    max_cycles integer not null,
    repo_root text not null,
    contexts_json text not null,
    decisions_json text not null,
    results_json text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists ari_runtime_execution_plan_previews (
    id text primary key,
    goal_id text not null,
    objective text not null,
    status text not null,
    reason text not null,
    repo_root text not null,
    context_json text not null,
    memory_context_json text not null,
    planner_config_json text not null,
    planner_result_json text not null,
    decision_json text not null,
    validation_error text,
    created_at text not null
);

create table if not exists ari_runtime_coding_loop_retry_approvals (
    approval_id text primary key,
    source_coding_loop_result_id text not null,
    source_preview_id text,
    source_execution_run_id text,
    original_goal text not null,
    proposed_retry_goal text not null,
    proposed_retry_action_json text not null,
    proposed_retry_action_description text not null,
    reason text not null,
    failed_verification_summary text not null,
    approval_status text not null,
    approval_json text not null,
    retry_execution_requires_approval integer not null,
    proposed_action_requires_approval integer not null,
    retry_execution_run_id text,
    retry_execution_status text,
    retry_execution_reason text,
    prior_retry_approval_id text,
    prior_retry_execution_run_id text,
    next_retry_approval_id text,
    created_at text not null,
    updated_at text,
    executed_at text,
    rejected_by text,
    rejected_at text
);
