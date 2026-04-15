export const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  tags TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_runs (
  id TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  notes TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  goal TEXT NOT NULL,
  completion_criteria TEXT NOT NULL,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_milestones (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  completion_criteria TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_steps (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  milestone_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  completion_criteria TEXT NOT NULL,
  depends_on_step_ids_json TEXT NOT NULL,
  blocked_by_json TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  linked_task_id TEXT,
  linked_improvement_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  id TEXT PRIMARY KEY,
  user_role TEXT NOT NULL,
  device_label TEXT NOT NULL,
  user_agent TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS ari_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  autonomy_level TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_id TEXT,
  dedupe_key TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  autonomy_level TEXT NOT NULL,
  action_type TEXT NOT NULL,
  action_payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  dedupe_key TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orchestration_records (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  raw_output TEXT NOT NULL,
  status TEXT NOT NULL,
  classification TEXT,
  concise_summary TEXT NOT NULL,
  next_instruction TEXT NOT NULL,
  reasoning TEXT NOT NULL,
  escalation_required INTEGER NOT NULL,
  escalation_packet_json TEXT NOT NULL,
  alec_decision TEXT NOT NULL,
  parent_orchestration_id TEXT,
  linked_improvement_ids_json TEXT NOT NULL,
  verification_signal TEXT,
  linkage_mode TEXT NOT NULL,
  created_at TEXT NOT NULL,
  processed_at TEXT
);

CREATE TABLE IF NOT EXISTS self_improvements (
  id TEXT PRIMARY KEY,
  capability TEXT NOT NULL,
  missing_capability TEXT NOT NULL,
  why_it_matters TEXT NOT NULL,
  what_it_unlocks TEXT NOT NULL,
  smallest_slice TEXT NOT NULL,
  next_best_action TEXT NOT NULL,
  approval_required INTEGER NOT NULL,
  relative_priority TEXT NOT NULL,
  leverage_score INTEGER NOT NULL,
  urgency_score INTEGER NOT NULL,
  dependency_value_score INTEGER NOT NULL,
  autonomy_impact_score INTEGER NOT NULL,
  implementation_effort_score INTEGER NOT NULL,
  priority_score INTEGER NOT NULL,
  status TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  approval_id TEXT,
  task_id TEXT,
  instruction_orchestration_id TEXT,
  dispatch_orchestration_id TEXT,
  dispatch_mode TEXT,
  dispatch_evidence TEXT,
  consumed_at TEXT,
  consumer TEXT,
  completion_orchestration_id TEXT,
  completion_evidence TEXT,
  verification_orchestration_id TEXT,
  verification_evidence TEXT,
  reflection_json TEXT NOT NULL,
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  approved_at TEXT,
  queued_at TEXT,
  dispatched_at TEXT,
  completed_at TEXT,
  verified_at TEXT
);

CREATE TABLE IF NOT EXISTS builder_dispatch_records (
  id TEXT PRIMARY KEY,
  orchestration_id TEXT NOT NULL,
  linked_improvement_ids_json TEXT NOT NULL,
  mode TEXT NOT NULL,
  instruction TEXT NOT NULL,
  summary TEXT NOT NULL,
  reasoning TEXT NOT NULL,
  routing_state TEXT NOT NULL,
  dispatch_status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  dispatched_at TEXT NOT NULL,
  consumed_at TEXT,
  consumer TEXT,
  completion_orchestration_id TEXT,
  verification_orchestration_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_outcomes (
  item_key TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  item_id TEXT NOT NULL,
  title TEXT NOT NULL,
  state TEXT NOT NULL,
  stage TEXT NOT NULL,
  state_since TEXT NOT NULL,
  last_progress_at TEXT NOT NULL,
  completed_at TEXT,
  blocked_reason TEXT,
  failure_reason TEXT,
  verification_signal TEXT,
  next_action TEXT NOT NULL,
  evidence_mode TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS awareness_snapshots (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  summary TEXT NOT NULL,
  current_focus_json TEXT NOT NULL,
  tracking_json TEXT NOT NULL,
  recent_intent_json TEXT NOT NULL,
  signature TEXT NOT NULL,
  created_at TEXT NOT NULL
);
`;
