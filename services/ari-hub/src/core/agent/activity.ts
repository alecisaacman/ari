import type {
  ApprovalAction,
  ApprovalRecord,
  ApprovalStatus,
  AriEventRecord,
  AriEventType,
  AutonomyLevel
} from "@/src/core/agent/activity-types";
import { markImprovementApprovedFromApproval } from "@/src/core/agent/self-improvement";
import { saveCanonicalNote } from "@/src/core/ari-spine/notes-bridge";
import { getDatabase } from "@/src/core/db/database";
import { getActiveStateSnapshot, rememberOperatorDecision } from "@/src/core/memory/spine";
import { createTask, listTasks, rememberMemory } from "@/src/core/memory/repository";
import type { MemoryType, TaskRecord } from "@/src/core/memory/types";

export const AUTONOMY_MODEL = [
  {
    level: "report" as const,
    title: "Report",
    description: "ARI surfaces observations and useful signals."
  },
  {
    level: "propose" as const,
    title: "Propose",
    description: "ARI suggests a concrete action and asks for approval."
  },
  {
    level: "execute" as const,
    title: "Execute",
    description: "ARI performs low-risk actions and reports what changed."
  }
] as const;

function now(): string {
  return new Date().toISOString();
}

function parseJsonObject(raw: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function parseApprovalAction(raw: string): ApprovalAction {
  const parsed = parseJsonObject(raw);
  if (parsed.type === "create_task" && typeof parsed.title === "string") {
    return {
      type: "create_task",
      title: parsed.title,
      notes: typeof parsed.notes === "string" ? parsed.notes : ""
    };
  }

  if (parsed.type === "update_memory" && typeof parsed.title === "string" && typeof parsed.content === "string") {
    return {
      type: "update_memory",
      memoryType: parsed.memoryType === "fact" ? "fact" : "preference",
      title: parsed.title,
      content: parsed.content
    };
  }

  return {
    type: "save_note",
    title: typeof parsed.title === "string" ? parsed.title : "ARI Approval Note",
    content: typeof parsed.content === "string" ? parsed.content : ""
  };
}

export function recordAriEvent(input: {
  type: AriEventType;
  title: string;
  body: string;
  autonomyLevel: AutonomyLevel;
  status?: "open" | "done";
  approvalId?: string;
  dedupeKey?: string;
  metadata?: Record<string, unknown>;
}): AriEventRecord {
  const database = getDatabase();
  const record: AriEventRecord = {
    id: crypto.randomUUID(),
    type: input.type,
    title: input.title,
    body: input.body,
    autonomyLevel: input.autonomyLevel,
    status: input.status || "done",
    approvalId: input.approvalId,
    dedupeKey: input.dedupeKey,
    metadata: input.metadata || {},
    createdAt: now()
  };

  database
    .prepare(
      `INSERT INTO ari_events
        (id, type, title, body, autonomy_level, status, approval_id, dedupe_key, metadata_json, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      record.id,
      record.type,
      record.title,
      record.body,
      record.autonomyLevel,
      record.status,
      record.approvalId || null,
      record.dedupeKey || null,
      JSON.stringify(record.metadata),
      record.createdAt
    );

  return record;
}

export function listAriEvents(limit = 24): AriEventRecord[] {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT id, type, title, body, autonomy_level, status, approval_id, dedupe_key, metadata_json, created_at
       FROM ari_events
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    type: AriEventType;
    title: string;
    body: string;
    autonomy_level: AutonomyLevel;
    status: "open" | "done";
    approval_id: string | null;
    dedupe_key: string | null;
    metadata_json: string;
    created_at: string;
  }>;

  const events = rows.map((row) => ({
    id: row.id,
    type: row.type,
    title: row.title,
    body: row.body,
    autonomyLevel: row.autonomy_level,
    status: row.status,
    approvalId: row.approval_id || undefined,
    dedupeKey: row.dedupe_key || undefined,
    metadata: parseJsonObject(row.metadata_json),
    createdAt: row.created_at
  }));

  const approvalActionIds = new Set(
    events
      .filter((event) => event.type === "action_executed" && event.approvalId && event.metadata.resolvedFromApproval === true)
      .map((event) => event.approvalId as string)
  );

  return events
    .filter((event) => {
      if (event.type === "approval_requested" && event.status === "open") {
        return false;
      }

      if (
        event.type === "approval_resolved" &&
        event.approvalId &&
        event.metadata.decision === "approve" &&
        approvalActionIds.has(event.approvalId)
      ) {
        return false;
      }

      return true;
    })
    .slice(0, limit);
}

export function hasRecentEvent(dedupeKey: string, windowMinutes: number): boolean {
  const database = getDatabase();
  const threshold = new Date(Date.now() - windowMinutes * 60 * 1000).toISOString();
  const row = database
    .prepare("SELECT id FROM ari_events WHERE dedupe_key = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 1")
    .get(dedupeKey, threshold) as { id: string } | undefined;
  return Boolean(row);
}

export async function requestApproval(input: {
  title: string;
  body: string;
  action: ApprovalAction;
  autonomyLevel?: AutonomyLevel;
  dedupeKey?: string;
}): Promise<ApprovalRecord> {
  const database = getDatabase();
  if (input.dedupeKey) {
    const existing = database
      .prepare("SELECT id, title, body, autonomy_level, action_type, action_payload_json, status, dedupe_key, created_at, resolved_at, resolution_note FROM approvals WHERE dedupe_key = ? AND status = 'pending' LIMIT 1")
      .get(input.dedupeKey) as
      | {
          id: string;
          title: string;
          body: string;
          autonomy_level: AutonomyLevel;
          action_type: ApprovalAction["type"];
          action_payload_json: string;
          status: ApprovalStatus;
          dedupe_key: string | null;
          created_at: string;
          resolved_at: string | null;
          resolution_note: string;
        }
      | undefined;

    if (existing) {
      return {
        id: existing.id,
        title: existing.title,
        body: existing.body,
        autonomyLevel: existing.autonomy_level,
        actionType: existing.action_type,
        actionPayload: parseApprovalAction(existing.action_payload_json),
        status: existing.status,
        dedupeKey: existing.dedupe_key || undefined,
        createdAt: existing.created_at,
        resolvedAt: existing.resolved_at || undefined,
        resolutionNote: existing.resolution_note
      };
    }
  }

  const record: ApprovalRecord = {
    id: crypto.randomUUID(),
    title: input.title,
    body: input.body,
    autonomyLevel: input.autonomyLevel || "propose",
    actionType: input.action.type,
    actionPayload: input.action,
    status: "pending",
    dedupeKey: input.dedupeKey,
    createdAt: now(),
    resolutionNote: ""
  };

  database
    .prepare(
      `INSERT INTO approvals
        (id, title, body, autonomy_level, action_type, action_payload_json, status, dedupe_key, created_at, resolved_at, resolution_note)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      record.id,
      record.title,
      record.body,
      record.autonomyLevel,
      record.actionType,
      JSON.stringify(record.actionPayload),
      record.status,
      record.dedupeKey || null,
      record.createdAt,
      null,
      record.resolutionNote
    );

  recordAriEvent({
    type: "approval_requested",
    title: record.title,
    body: record.body,
    autonomyLevel: record.autonomyLevel,
    status: "open",
    approvalId: record.id,
    dedupeKey: record.dedupeKey ? `event:${record.dedupeKey}` : undefined,
    metadata: {
      actionType: record.actionType
    }
  });

  return record;
}

export function listPendingApprovals(limit = 6): ApprovalRecord[] {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT id, title, body, autonomy_level, action_type, action_payload_json, status, dedupe_key, created_at, resolved_at, resolution_note
       FROM approvals
       WHERE status = 'pending'
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    title: string;
    body: string;
    autonomy_level: AutonomyLevel;
    action_type: ApprovalAction["type"];
    action_payload_json: string;
    status: ApprovalStatus;
    dedupe_key: string | null;
    created_at: string;
    resolved_at: string | null;
    resolution_note: string;
  }>;

  return rows.map((row) => ({
    id: row.id,
    title: row.title,
    body: row.body,
    autonomyLevel: row.autonomy_level,
    actionType: row.action_type,
    actionPayload: parseApprovalAction(row.action_payload_json),
    status: row.status,
    dedupeKey: row.dedupe_key || undefined,
    createdAt: row.created_at,
    resolvedAt: row.resolved_at || undefined,
    resolutionNote: row.resolution_note
  }));
}

async function executeApprovalAction(action: ApprovalAction): Promise<{ title: string; body: string }> {
  if (action.type === "save_note") {
    const note = await saveCanonicalNote(action.title, action.content);
    return {
      title: `Approved note "${note.title}" saved`,
      body: "ARI stored the approved note in the canonical ARI spine."
    };
  }

  if (action.type === "create_task") {
    const task = createTask(action.title, action.notes);
    return {
      title: `Approved task "${task.title}" created`,
      body: "ARI stored the approved task in the canonical ARI spine and surfaced it through the hub."
    };
  }

  const memory = rememberMemory(action.memoryType, action.title, action.content);
  return {
    title: `Approved ${memory.type} "${memory.title}" stored`,
    body: `ARI stored the approved ${memory.type} in the canonical ARI spine.`
  };
}

export async function resolveApproval(approvalId: string, decision: "approve" | "deny"): Promise<ApprovalRecord> {
  const database = getDatabase();
  const row = database
    .prepare(
      `SELECT id, title, body, autonomy_level, action_type, action_payload_json, status, dedupe_key, created_at, resolved_at, resolution_note
       FROM approvals
       WHERE id = ?`
    )
    .get(approvalId) as
    | {
        id: string;
        title: string;
        body: string;
        autonomy_level: AutonomyLevel;
        action_type: ApprovalAction["type"];
        action_payload_json: string;
        status: ApprovalStatus;
        dedupe_key: string | null;
        created_at: string;
        resolved_at: string | null;
        resolution_note: string;
      }
    | undefined;

  if (!row) {
    throw new Error("Approval was not found.");
  }

  if (row.status !== "pending") {
    throw new Error("Approval has already been resolved.");
  }

  const resolvedAt = now();
  let resolutionNote = decision === "approve" ? "Approved and executed." : "Denied by operator.";

  if (decision === "approve") {
    const action = parseApprovalAction(row.action_payload_json);
    const actionResult = await executeApprovalAction(action);
    resolutionNote = actionResult.body;
    rememberOperatorDecision(row.title, resolutionNote, ["approval", decision]);
    markImprovementApprovedFromApproval(row.id, action.type === "create_task" ? action.title : undefined);
    recordAriEvent({
      type: "action_executed",
      title: actionResult.title,
      body: actionResult.body,
      autonomyLevel: "execute",
      approvalId: row.id,
      metadata: { resolvedFromApproval: true }
    });
  }

  if (decision === "deny") {
    rememberOperatorDecision(row.title, resolutionNote, ["approval", decision]);
  }

  database
    .prepare("UPDATE approvals SET status = ?, resolved_at = ?, resolution_note = ? WHERE id = ?")
    .run(decision === "approve" ? "approved" : "denied", resolvedAt, resolutionNote, approvalId);

  recordAriEvent({
    type: "approval_resolved",
    title: decision === "approve" ? `Approval granted: ${row.title}` : `Approval denied: ${row.title}`,
    body: resolutionNote,
    autonomyLevel: "report",
    approvalId: row.id,
    metadata: { decision }
  });

  return {
    id: row.id,
    title: row.title,
    body: row.body,
    autonomyLevel: row.autonomy_level,
    actionType: row.action_type,
    actionPayload: parseApprovalAction(row.action_payload_json),
    status: decision === "approve" ? "approved" : "denied",
    dedupeKey: row.dedupe_key || undefined,
    createdAt: row.created_at,
    resolvedAt,
    resolutionNote
  };
}

export function buildTaskSummary(tasks: TaskRecord[], limit = 4): string {
  const slice = tasks.slice(0, limit);
  if (!slice.length) {
    return "No open tasks.";
  }

  return slice.map((task, index) => `${index + 1}. ${task.title}`).join("\n");
}

export function createFocusBriefApproval(tasks: TaskRecord[]): Promise<ApprovalRecord> {
  const topTask = tasks[0];
  const state = getActiveStateSnapshot();
  const currentPriority = state.currentPriorities[0]?.content;
  const content = [
    "ARI focus brief",
    "",
    `Lead task: ${topTask?.title || "None"}`,
    currentPriority ? `Current priority: ${currentPriority}` : "",
    "",
    "Open tasks:",
    buildTaskSummary(tasks)
  ]
    .filter(Boolean)
    .join("\n");

  return requestApproval({
    title: "Create focus brief",
    body: topTask
      ? `ARI can generate a short note centered on "${topTask.title}"${currentPriority ? ` and keep it aligned with "${currentPriority}".` : "."} Approve?`
      : "ARI can generate a short focus brief. Approve?",
    action: {
      type: "save_note",
      title: `ARI Focus Brief ${new Date().toISOString().slice(0, 10)}`,
      content
    },
    autonomyLevel: "propose",
    dedupeKey: topTask ? `approval:focus-brief:${topTask.id}` : "approval:focus-brief"
  });
}
