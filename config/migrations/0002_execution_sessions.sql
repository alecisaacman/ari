alter table ari_execution_tasks add column lifecycle_state text not null default 'waiting_for_worker';
alter table ari_execution_tasks add column restrictions_json text not null default '[]';
alter table ari_execution_tasks add column authority_scope_json text not null default '{}';
alter table ari_execution_tasks add column approval_state_json text not null default '{}';
alter table ari_execution_tasks add column active_attempt_id text;
alter table ari_execution_tasks add column pause_reason text;
alter table ari_execution_tasks add column cancel_reason text;
alter table ari_execution_tasks add column recovery_block_reason text;

alter table ari_execution_attempts add column lifecycle_state text not null default 'waiting_for_worker';
alter table ari_execution_attempts add column session_id text;
alter table ari_execution_attempts add column worker_identity text;
alter table ari_execution_attempts add column worker_session_ref text;
alter table ari_execution_attempts add column lease_started_at text;
alter table ari_execution_attempts add column lease_expires_at text;
alter table ari_execution_attempts add column last_seen_at text;
alter table ari_execution_attempts add column prior_attempt_id text;
alter table ari_execution_attempts add column replacement_attempt_id text;
alter table ari_execution_attempts add column recovery_json text;
alter table ari_execution_attempts add column continuation_packet_id text;
alter table ari_execution_attempts add column continuation_acknowledgement_id text;
alter table ari_execution_attempts add column waiting_reason text;

alter table ari_execution_checkpoints add column restrictions_json text not null default '[]';
alter table ari_execution_checkpoints add column authority_scope_json text not null default '{}';
alter table ari_execution_checkpoints add column approval_state_json text not null default '{}';

create unique index if not exists idx_execution_attempts_session
    on ari_execution_attempts(session_id) where session_id is not null;
create index if not exists idx_execution_attempts_lease
    on ari_execution_attempts(lifecycle_state, lease_expires_at);

create table if not exists ari_execution_worker_heartbeats (
    heartbeat_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null references ari_execution_attempts(attempt_id),
    session_id text not null,
    lease_owner text not null,
    observed_at text not null,
    lease_expires_at text not null,
    metadata_json text not null
);

create table if not exists ari_execution_continuation_packets (
    packet_id text primary key,
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null unique references ari_execution_attempts(attempt_id),
    prior_attempt_id text not null references ari_execution_attempts(attempt_id),
    checkpoint_id text not null references ari_execution_checkpoints(checkpoint_id),
    packet_json text not null,
    payload_sha256 text not null,
    created_at text not null
);

create table if not exists ari_execution_continuation_acknowledgements (
    acknowledgement_id text primary key,
    packet_id text not null unique references ari_execution_continuation_packets(packet_id),
    task_id text not null references ari_execution_tasks(task_id),
    attempt_id text not null unique references ari_execution_attempts(attempt_id),
    worker_identity text not null,
    acknowledgement_json text not null,
    payload_sha256 text not null,
    created_at text not null
);

create index if not exists idx_execution_heartbeats_attempt
    on ari_execution_worker_heartbeats(attempt_id, observed_at);
