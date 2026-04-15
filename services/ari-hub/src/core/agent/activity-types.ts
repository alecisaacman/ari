export type AutonomyLevel = "report" | "propose" | "execute";

export type AriEventType =
  | "note_saved"
  | "task_created"
  | "task_completed"
  | "memory_updated"
  | "suggestion_generated"
  | "observation_generated"
  | "approval_requested"
  | "approval_resolved"
  | "action_executed"
  | "background_action_executed"
  | "background_job_started"
  | "background_job_completed"
  | "orchestration_received"
  | "orchestration_classified"
  | "orchestration_summary_generated"
  | "orchestration_next_instruction"
  | "orchestration_escalation_requested";

export type AriEventRecord = {
  id: string;
  type: AriEventType;
  title: string;
  body: string;
  autonomyLevel: AutonomyLevel;
  status: "open" | "done";
  approvalId?: string;
  dedupeKey?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
};

export type ApprovalStatus = "pending" | "approved" | "denied";

export type ApprovalAction =
  | { type: "save_note"; title: string; content: string }
  | { type: "create_task"; title: string; notes: string }
  | { type: "update_memory"; memoryType: "fact" | "preference"; title: string; content: string };

export type ApprovalRecord = {
  id: string;
  title: string;
  body: string;
  autonomyLevel: AutonomyLevel;
  actionType: ApprovalAction["type"];
  actionPayload: ApprovalAction;
  status: ApprovalStatus;
  dedupeKey?: string;
  createdAt: string;
  resolvedAt?: string;
  resolutionNote: string;
};
