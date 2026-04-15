import type { OrchestrationMode } from "@/src/core/config";
import {
  detectCanonicalCapabilityGaps,
  getCanonicalTopImprovementFocus
} from "@/src/core/ari-spine/policy-bridge";
import {
  getCanonicalCoordinationRecord,
  listCanonicalCoordinationRecords,
  putCanonicalCoordinationRecord
} from "@/src/core/ari-spine/coordination-bridge";
import { getDatabase } from "@/src/core/db/database";
import { findLatestTaskByTitle, listTasks } from "@/src/core/memory/repository";
import { findLatestDispatchRecordByOrchestrationId } from "@/src/core/orchestration/dispatch-records";
import type {
  ExecutionEvidenceMode,
  ImprovementPriority,
  ImprovementRecord,
  ImprovementReflection,
  ImprovementStatus
} from "@/src/core/memory/types";

type ImprovementDraft = {
  capability: string;
  missingCapability: string;
  whyItMatters: string;
  whatItUnlocks: string;
  smallestSlice: string;
  nextBestAction: string;
  approvalRequired: boolean;
  leverage: number;
  urgency: number;
  dependencyValue: number;
  autonomyImpact: number;
  implementationEffort: number;
  priorityScore: number;
  relativePriority: ImprovementPriority;
  reflection: ImprovementReflection;
  approvalTitle: string;
  approvalBody: string;
  taskTitle: string;
  taskNotes: string;
  suggestionTitle: string;
  suggestionBody: string;
  reply: string;
  dedupeKey: string;
  keywords: string[];
};

type ImprovementRule = {
  capability: string;
  keywords: string[];
  pattern: RegExp;
  baseScores: {
    leverage: number;
    urgency: number;
    dependencyValue: number;
    autonomyImpact: number;
    implementationEffort: number;
  };
  build: (
    message: string,
    reflection: ImprovementReflection
  ) => Omit<
    ImprovementDraft,
    | "priorityScore"
    | "relativePriority"
    | "reflection"
    | "dedupeKey"
    | "keywords"
    | "leverage"
    | "urgency"
    | "dependencyValue"
    | "autonomyImpact"
    | "implementationEffort"
  >;
};

type ImprovementRow = {
  id: string;
  capability: string;
  missing_capability: string;
  why_it_matters: string;
  what_it_unlocks: string;
  smallest_slice: string;
  next_best_action: string;
  approval_required: number;
  relative_priority: ImprovementPriority;
  leverage_score: number;
  urgency_score: number;
  dependency_value_score: number;
  autonomy_impact_score: number;
  implementation_effort_score: number;
  priority_score: number;
  status: ImprovementStatus;
  dedupe_key: string;
  approval_id: string | null;
  task_id: string | null;
  instruction_orchestration_id: string | null;
  dispatch_record_id: string | null;
  dispatch_orchestration_id: string | null;
  dispatch_mode: OrchestrationMode | null;
  dispatch_evidence: ExecutionEvidenceMode | null;
  consumed_at: string | null;
  consumer: string | null;
  completion_orchestration_id: string | null;
  completion_evidence: ExecutionEvidenceMode | null;
  verification_orchestration_id: string | null;
  verification_evidence: ExecutionEvidenceMode | null;
  reflection_json: string;
  first_observed_at: string;
  last_observed_at: string;
  approved_at: string | null;
  queued_at: string | null;
  dispatched_at: string | null;
  completed_at: string | null;
  verified_at: string | null;
};

function now(): string {
  return new Date().toISOString();
}

function normalizeQuoted(message: string): string {
  return message.trim().replace(/\s+/g, " ");
}

function parseJsonObject<T>(raw: string, fallback: T): T {
  try {
    const parsed = JSON.parse(raw) as T;
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function clampCount(value: number): number {
  if (!Number.isFinite(value) || value <= 0) {
    return 0;
  }
  return Math.min(Math.round(value), 4);
}

function computePriority(
  scores: Pick<ImprovementDraft, "leverage" | "urgency" | "dependencyValue" | "autonomyImpact" | "implementationEffort">,
  reflection: ImprovementReflection
): { priorityScore: number; relativePriority: ImprovementPriority } {
  const base =
    scores.leverage * 4 +
    scores.urgency * 3 +
    scores.dependencyValue * 3 +
    scores.autonomyImpact * 4 -
    scores.implementationEffort * 2;
  const reflectionBonus =
    reflection.repeatedLimitations * 2 +
    reflection.repeatedUserFriction * 3 +
    reflection.repeatedManualSteps * 2 +
    reflection.repeatedEscalationCauses * 3;
  const priorityScore = base + reflectionBonus;

  if (priorityScore >= 45) {
    return { priorityScore, relativePriority: "highest" };
  }
  if (priorityScore >= 33) {
    return { priorityScore, relativePriority: "high" };
  }
  return { priorityScore, relativePriority: "medium" };
}

const RULES: ImprovementRule[] = [
  {
    capability: "interface-control",
    keywords: ["interface", "ui", "click", "scroll", "tap", "control"],
    pattern:
      /\b(click|tap|scroll|open that|close that|control the interface|control the ui|direct interface control|independent interface control|use the interface)\b/i,
    baseScores: {
      leverage: 5,
      urgency: 4,
      dependencyValue: 5,
      autonomyImpact: 5,
      implementationEffort: 3
    },
    build(message, reflection) {
      const recurring = reflection.total >= 3 ? "This limitation is recurring and is now a real autonomy bottleneck." : "";
      return {
        capability: "interface-control",
        missingCapability: "direct interface control",
        whyItMatters: "Interface execution still depends on Alec relaying actions by hand.",
        whatItUnlocks: "ARI can operate the hub directly instead of stopping at instructions.",
        smallestSlice: "Ship a safe interface-control bridge for click, scroll, and element targeting inside ACE.",
        nextBestAction: "Queue the interface-control bridge now and make it the next builder slice.",
        approvalRequired: true,
        approvalTitle: "Queue interface-control bridge",
        approvalBody: "Missing capability: direct interface control. Approve and ARI will queue the bridge as the next implementation slice.",
        taskTitle: "Implement interface-control bridge for ACE",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build the safe interface-control bridge now so ARI can act on the hub directly instead of routing this class of work through Alec.`,
        suggestionTitle: "Make interface control the next ARI upgrade",
        suggestionBody: [recurring, "ARI is still blocked from direct interface execution. The next best move is to ship the interface-control bridge immediately."]
          .filter(Boolean)
          .join(" "),
        reply: `Missing capability: direct interface control. Why it matters: interface execution still depends on handoff. What it unlocks: ARI can act on the hub directly. Smallest slice: ship the safe interface-control bridge now.`
      };
    }
  },
  {
    capability: "artifact-generation",
    keywords: ["artifact", "generate", "export", "pdf", "docx", "document", "image", "slides", "deck", "report"],
    pattern: /\b(generate|create|export|produce)\b.*\b(pdf|docx|document|artifact|report|image|deck|slide|slides)\b/i,
    baseScores: {
      leverage: 4,
      urgency: 3,
      dependencyValue: 4,
      autonomyImpact: 4,
      implementationEffort: 3
    },
    build(message, reflection) {
      const recurring = reflection.repeatedUserFriction >= 2 ? "This request pattern is repeating, so the missing generation path is now costing time." : "";
      return {
        capability: "artifact-generation",
        missingCapability: "direct artifact generation pipeline",
        whyItMatters: "ARI can prepare content but still cannot finish the requested artifact directly.",
        whatItUnlocks: "ARI can turn prepared content into real exported outputs without a second tool hop.",
        smallestSlice: "Add one direct generation path for the requested artifact family with a saved output contract.",
        nextBestAction: "Queue the artifact-generation pipeline now so prepared content can become executable output.",
        approvalRequired: true,
        approvalTitle: "Queue artifact-generation pipeline",
        approvalBody: "Missing capability: direct artifact-generation pipeline. Approve and ARI will queue the smallest generation slice now.",
        taskTitle: "Add artifact-generation pipeline",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build the smallest direct generation/export path now so ARI can produce the requested artifact directly instead of stopping at preparation.`,
        suggestionTitle: "Add the missing artifact pipeline",
        suggestionBody: [recurring, "ARI should stop ending artifact requests at planning. The next implementation slice is the direct generation path."]
          .filter(Boolean)
          .join(" "),
        reply: `Missing capability: direct artifact generation. Why it matters: ARI can prepare content but not finish the output. What it unlocks: direct exported artifacts. Smallest slice: add the requested generation path now.`
      };
    }
  },
  {
    capability: "notification-delivery",
    keywords: ["notification", "notify", "alert", "phone", "browser"],
    pattern: /\b(push notification|browser notification|notify me|iphone notification|phone notification|alert me)\b/i,
    baseScores: {
      leverage: 4,
      urgency: 3,
      dependencyValue: 3,
      autonomyImpact: 4,
      implementationEffort: 2
    },
    build(message, reflection) {
      const recurring = reflection.repeatedManualSteps >= 2 ? "This is repeatedly falling back to hub-only visibility, which is now a coordination drag." : "";
      return {
        capability: "notification-delivery",
        missingCapability: "notification delivery channel",
        whyItMatters: "Important approvals and alerts still depend on Alec opening the hub at the right moment.",
        whatItUnlocks: "ARI can surface urgent state outside the browser tab and tighten the approval loop.",
        smallestSlice: "Add one reliable browser-or-phone notification channel for approvals and high-signal alerts.",
        nextBestAction: "Queue the notification delivery slice now so important signals can leave the hub cleanly.",
        approvalRequired: true,
        approvalTitle: "Queue notification delivery channel",
        approvalBody: "Missing capability: notification delivery channel. Approve and ARI will queue the smallest delivery slice now.",
        taskTitle: "Add notification delivery channel",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build browser or phone notification delivery now so ARI can push approvals and important alerts beyond the hub.`,
        suggestionTitle: "Push signals beyond the hub",
        suggestionBody: [recurring, "ARI identified notification delivery as the next clean way to reduce missed approvals and alerts."]
          .filter(Boolean)
          .join(" "),
        reply: `Missing capability: notification delivery. Why it matters: approvals and alerts stay trapped in the hub. What it unlocks: timely signals outside the browser. Smallest slice: add the first delivery channel now.`
      };
    }
  }
];

function collectTextRows(query: string, params: Array<string | number | null> = []): string[] {
  const database = getDatabase();
  return (database.prepare(query).all(...params) as Array<{ text_value: string }>).map((row) => row.text_value);
}

function countPatternMatches(values: string[], pattern: RegExp): number {
  let count = 0;
  for (const value of values) {
    const matcher = new RegExp(pattern.source, pattern.flags);
    if (matcher.test(value)) {
      count += 1;
    }
  }
  return count;
}

function collectReflectionSignals(rule: ImprovementRule): ImprovementReflection {
  const messages = collectTextRows(
    `SELECT content AS text_value
     FROM messages
     WHERE role = 'user'
     ORDER BY created_at DESC
     LIMIT 40`
  );
  const escalations = listCanonicalCoordinationRecords<{
    raw_output: string;
    escalation_required: number;
    created_at: string;
  }>("orchestration_record", 30)
    .filter((row) => row.escalation_required === 1)
    .map((row) => row.raw_output);
  const approvals = collectTextRows(
    `SELECT title || ' ' || body AS text_value
     FROM approvals
     WHERE dedupe_key = ?
     ORDER BY created_at DESC
     LIMIT 20`,
    [`capability-gap:${rule.capability}`]
  );
  const taskNotes = listTasks(30).map((task) => `${task.title} ${task.notes}`);

  const repeatedUserFriction = clampCount(countPatternMatches(messages, rule.pattern));
  const repeatedEscalationCauses = clampCount(countPatternMatches(escalations, rule.pattern));
  const repeatedLimitations = clampCount(approvals.length);
  const repeatedManualSteps = clampCount(countPatternMatches(taskNotes, rule.pattern));
  const total = repeatedLimitations + repeatedUserFriction + repeatedManualSteps + repeatedEscalationCauses;

  return {
    repeatedLimitations,
    repeatedUserFriction,
    repeatedManualSteps,
    repeatedEscalationCauses,
    total
  };
}

function collectRecentUserMessages(limit = 40): string[] {
  return collectTextRows(
    `SELECT content AS text_value
     FROM messages
     WHERE role = 'user'
     ORDER BY created_at DESC
     LIMIT ?`,
    [limit]
  );
}

function collectEscalationTexts(limit = 30): string[] {
  return listCanonicalCoordinationRecords<{
    raw_output: string;
    escalation_required: number;
    created_at: string;
  }>("orchestration_record", limit)
    .filter((row) => row.escalation_required === 1)
    .map((row) => row.raw_output);
}

function collectApprovalCountsByCapability(): Record<string, number> {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT dedupe_key, COUNT(*) AS count
       FROM approvals
       WHERE dedupe_key LIKE 'capability-gap:%'
       GROUP BY dedupe_key`
    )
    .all() as Array<{ dedupe_key: string; count: number }>;

  return rows.reduce<Record<string, number>>((acc, row) => {
    const capability = row.dedupe_key.replace(/^capability-gap:/, "");
    if (capability) {
      acc[capability] = row.count;
    }
    return acc;
  }, {});
}

function statusRank(status: ImprovementStatus): number {
  switch (status) {
    case "proposed":
      return 0;
    case "approved":
      return 1;
    case "queued":
      return 2;
    case "dispatched":
      return 3;
    case "completed":
      return 4;
    case "verified":
      return 5;
  }
}

function mapImprovementRow(row: ImprovementRow): ImprovementRecord {
  return {
    id: row.id,
    capability: row.capability,
    missingCapability: row.missing_capability,
    whyItMatters: row.why_it_matters,
    whatItUnlocks: row.what_it_unlocks,
    smallestSlice: row.smallest_slice,
    nextBestAction: row.next_best_action,
    approvalRequired: Boolean(row.approval_required),
    relativePriority: row.relative_priority,
    leverage: row.leverage_score,
    urgency: row.urgency_score,
    dependencyValue: row.dependency_value_score,
    autonomyImpact: row.autonomy_impact_score,
    implementationEffort: row.implementation_effort_score,
    priorityScore: row.priority_score,
    status: row.status,
    approvalId: row.approval_id || undefined,
    taskId: row.task_id || undefined,
    dedupeKey: row.dedupe_key,
    instructionOrchestrationId: row.instruction_orchestration_id || undefined,
    dispatchRecordId: row.dispatch_record_id || undefined,
    dispatchOrchestrationId: row.dispatch_orchestration_id || undefined,
    dispatchMode: row.dispatch_mode || undefined,
    dispatchEvidence: row.dispatch_evidence || undefined,
    consumedAt: row.consumed_at || undefined,
    consumer: row.consumer || undefined,
    completionOrchestrationId: row.completion_orchestration_id || undefined,
    completionEvidence: row.completion_evidence || undefined,
    verificationOrchestrationId: row.verification_orchestration_id || undefined,
    verificationEvidence: row.verification_evidence || undefined,
    reflection: parseJsonObject<ImprovementReflection>(row.reflection_json, {
      repeatedLimitations: 0,
      repeatedUserFriction: 0,
      repeatedManualSteps: 0,
      repeatedEscalationCauses: 0,
      total: 0
    }),
    firstObservedAt: row.first_observed_at,
    lastObservedAt: row.last_observed_at,
    approvedAt: row.approved_at || undefined,
    queuedAt: row.queued_at || undefined,
    dispatchedAt: row.dispatched_at || undefined,
    completedAt: row.completed_at || undefined,
    verifiedAt: row.verified_at || undefined
  };
}

function recordToImprovementRow(record: ImprovementRecord): ImprovementRow {
  return {
    id: record.id,
    capability: record.capability,
    missing_capability: record.missingCapability,
    why_it_matters: record.whyItMatters,
    what_it_unlocks: record.whatItUnlocks,
    smallest_slice: record.smallestSlice,
    next_best_action: record.nextBestAction,
    approval_required: record.approvalRequired ? 1 : 0,
    relative_priority: record.relativePriority,
    leverage_score: record.leverage,
    urgency_score: record.urgency,
    dependency_value_score: record.dependencyValue,
    autonomy_impact_score: record.autonomyImpact,
    implementation_effort_score: record.implementationEffort,
    priority_score: record.priorityScore,
    status: record.status,
    dedupe_key: record.dedupeKey,
    approval_id: record.approvalId || null,
    task_id: record.taskId || null,
    instruction_orchestration_id: record.instructionOrchestrationId || null,
    dispatch_record_id: record.dispatchRecordId || null,
    dispatch_orchestration_id: record.dispatchOrchestrationId || null,
    dispatch_mode: record.dispatchMode || null,
    dispatch_evidence: record.dispatchEvidence || null,
    consumed_at: record.consumedAt || null,
    consumer: record.consumer || null,
    completion_orchestration_id: record.completionOrchestrationId || null,
    completion_evidence: record.completionEvidence || null,
    verification_orchestration_id: record.verificationOrchestrationId || null,
    verification_evidence: record.verificationEvidence || null,
    reflection_json: JSON.stringify(record.reflection),
    first_observed_at: record.firstObservedAt,
    last_observed_at: record.lastObservedAt,
    approved_at: record.approvedAt || null,
    queued_at: record.queuedAt || null,
    dispatched_at: record.dispatchedAt || null,
    completed_at: record.completedAt || null,
    verified_at: record.verifiedAt || null
  };
}

function findRule(capability: string): ImprovementRule | undefined {
  return RULES.find((rule) => rule.capability === capability);
}

function listImprovementRows(limit = 12): ImprovementRow[] {
  return listCanonicalCoordinationRecords<ImprovementRow>("self_improvement", limit);
}

export function detectRankedCapabilityGaps(message: string): ImprovementDraft[] {
  if (!message.trim()) {
    return [];
  }
  return detectCanonicalCapabilityGaps({
    message,
    recentMessages: collectRecentUserMessages(40),
    taskNotes: listTasks(30).map((task) => `${task.title} ${task.notes}`),
    escalationTexts: collectEscalationTexts(30),
    approvalCounts: collectApprovalCountsByCapability()
  }) as ImprovementDraft[];
}

export function getTopRankedCapabilityGap(message: string): ImprovementDraft | null {
  return detectRankedCapabilityGaps(message)[0] || null;
}

export function upsertImprovementProposal(proposal: ImprovementDraft, approvalId?: string): ImprovementRecord {
  const existing = listImprovementRows(100).find((row) => row.dedupe_key === proposal.dedupeKey);

  const timestamp = now();

  if (!existing) {
    const id = crypto.randomUUID();
    putCanonicalCoordinationRecord<ImprovementRow>("self_improvement", {
      id,
      capability: proposal.capability,
      missing_capability: proposal.missingCapability,
      why_it_matters: proposal.whyItMatters,
      what_it_unlocks: proposal.whatItUnlocks,
      smallest_slice: proposal.smallestSlice,
      next_best_action: proposal.nextBestAction,
      approval_required: proposal.approvalRequired ? 1 : 0,
      relative_priority: proposal.relativePriority,
      leverage_score: proposal.leverage,
      urgency_score: proposal.urgency,
      dependency_value_score: proposal.dependencyValue,
      autonomy_impact_score: proposal.autonomyImpact,
      implementation_effort_score: proposal.implementationEffort,
      priority_score: proposal.priorityScore,
      status: "proposed",
      dedupe_key: proposal.dedupeKey,
      approval_id: approvalId || null,
      task_id: null,
      instruction_orchestration_id: null,
      dispatch_record_id: null,
      dispatch_orchestration_id: null,
      dispatch_mode: null,
      dispatch_evidence: null,
      consumed_at: null,
      consumer: null,
      completion_orchestration_id: null,
      completion_evidence: null,
      verification_orchestration_id: null,
      verification_evidence: null,
      reflection_json: JSON.stringify(proposal.reflection),
      first_observed_at: timestamp,
      last_observed_at: timestamp,
      approved_at: null,
      queued_at: null,
      dispatched_at: null,
      completed_at: null,
      verified_at: null
    });

    return getImprovementByDedupeKey(proposal.dedupeKey)!;
  }

  putCanonicalCoordinationRecord<ImprovementRow>("self_improvement", {
    ...existing,
    missing_capability: proposal.missingCapability,
    why_it_matters: proposal.whyItMatters,
    what_it_unlocks: proposal.whatItUnlocks,
    smallest_slice: proposal.smallestSlice,
    next_best_action: proposal.nextBestAction,
    approval_required: proposal.approvalRequired ? 1 : 0,
    relative_priority: proposal.relativePriority,
    leverage_score: proposal.leverage,
    urgency_score: proposal.urgency,
    dependency_value_score: proposal.dependencyValue,
    autonomy_impact_score: proposal.autonomyImpact,
    implementation_effort_score: proposal.implementationEffort,
    priority_score: proposal.priorityScore,
    approval_id: approvalId || existing.approval_id,
    reflection_json: JSON.stringify(proposal.reflection),
    last_observed_at: timestamp
  });

  return getImprovementByDedupeKey(proposal.dedupeKey)!;
}

function updateImprovementStatus(
  id: string,
  nextStatus: ImprovementStatus,
  patch: Partial<{
    approvalId: string;
    taskId: string;
    instructionOrchestrationId: string;
    dispatchRecordId: string;
    dispatchOrchestrationId: string;
    dispatchMode: OrchestrationMode;
    dispatchEvidence: ExecutionEvidenceMode;
    consumedAt: string;
    consumer: string;
    completionOrchestrationId: string;
    completionEvidence: ExecutionEvidenceMode;
    verificationOrchestrationId: string;
    verificationEvidence: ExecutionEvidenceMode;
    approvedAt: string;
    queuedAt: string;
    dispatchedAt: string;
    completedAt: string;
    verifiedAt: string;
  }> = {}
): ImprovementRecord | null {
  const current = getImprovementById(id);
  if (!current || statusRank(nextStatus) < statusRank(current.status)) {
    return current;
  }

  const updated: ImprovementRecord = {
    ...current,
    status: nextStatus,
    approvalId: patch.approvalId || current.approvalId,
    taskId: patch.taskId || current.taskId,
    instructionOrchestrationId: patch.instructionOrchestrationId || current.instructionOrchestrationId,
    dispatchRecordId: patch.dispatchRecordId || current.dispatchRecordId,
    dispatchOrchestrationId: patch.dispatchOrchestrationId || current.dispatchOrchestrationId,
    dispatchMode: patch.dispatchMode || current.dispatchMode,
    dispatchEvidence: patch.dispatchEvidence || current.dispatchEvidence,
    consumedAt: patch.consumedAt || current.consumedAt,
    consumer: patch.consumer || current.consumer,
    completionOrchestrationId: patch.completionOrchestrationId || current.completionOrchestrationId,
    completionEvidence: patch.completionEvidence || current.completionEvidence,
    verificationOrchestrationId: patch.verificationOrchestrationId || current.verificationOrchestrationId,
    verificationEvidence: patch.verificationEvidence || current.verificationEvidence,
    approvedAt: patch.approvedAt || current.approvedAt,
    queuedAt: patch.queuedAt || current.queuedAt,
    dispatchedAt: patch.dispatchedAt || current.dispatchedAt,
    completedAt: patch.completedAt || current.completedAt,
    verifiedAt: patch.verifiedAt || current.verifiedAt,
    lastObservedAt: now()
  };
  putCanonicalCoordinationRecord<ImprovementRow>("self_improvement", recordToImprovementRow(updated));
  return getImprovementById(id);
}

export function markImprovementApprovedFromApproval(approvalId: string, taskTitle?: string): ImprovementRecord | null {
  const row = listImprovementRows(100).find((candidate) => candidate.approval_id === approvalId);
  if (!row) {
    return null;
  }

  const timestamp = now();
  const approved = updateImprovementStatus(row.id, "approved", { approvalId, approvedAt: timestamp });
  if (!approved) {
    return null;
  }

  const task = taskTitle ? findLatestTaskByTitle(taskTitle) : null;
  if (!taskTitle) {
    return approved;
  }

  return updateImprovementStatus(row.id, "queued", {
    approvalId,
    approvedAt: approved.approvedAt || timestamp,
    queuedAt: timestamp,
    taskId: task?.id
  });
}

export function markImprovementLinkedToInstruction(
  orchestrationId: string,
  mode: OrchestrationMode,
  linkedImprovementIds: string[],
  evidence: ExecutionEvidenceMode,
  dispatchRecordId?: string
): ImprovementRecord[] {
  const updated: ImprovementRecord[] = [];
  for (const improvementId of linkedImprovementIds.filter(Boolean)) {
    const next = updateImprovementStatus(improvementId, "dispatched", {
      instructionOrchestrationId: orchestrationId,
      dispatchRecordId,
      dispatchOrchestrationId: orchestrationId,
      dispatchMode: mode,
      dispatchEvidence: evidence,
      dispatchedAt: now()
    });
    if (next) {
      updated.push(next);
    }
  }
  return updated;
}

export function markImprovementDispatchedFromInstruction(instruction: string): ImprovementRecord[] {
  const normalized = instruction.toLowerCase();
  const active = listImprovementLifecycle(8).filter((item) => statusRank(item.status) < statusRank("dispatched"));
  const updated: ImprovementRecord[] = [];

  for (const item of active) {
    const rule = findRule(item.capability);
    if (!rule) {
      continue;
    }
    if (rule.keywords.some((keyword) => normalized.includes(keyword))) {
      const next = updateImprovementStatus(item.id, "dispatched", {
        dispatchedAt: now(),
        dispatchEvidence: "inferred"
      });
      if (next) {
        updated.push(next);
      }
    }
  }

  return updated;
}

export function markImprovementConsumedFromDispatch(dispatchRecordId: string, consumer: string): ImprovementRecord[] {
  const consumedAt = now();
  return listImprovementLifecycle(100)
    .filter((item) => item.dispatchRecordId === dispatchRecordId && !item.consumedAt)
    .map((item) =>
      updateImprovementStatus(item.id, item.status, {
        consumedAt,
        consumer
      })
    )
    .filter((item): item is ImprovementRecord => Boolean(item));
}

export function markImprovementProgressFromBuilderOutput(record: {
  id: string;
  rawOutput: string;
  parentOrchestrationId?: string;
  linkedImprovementIds: string[];
  verificationSignal?: "completed" | "verified";
  linkageMode: "explicit" | "heuristic";
}): ImprovementRecord[] {
  const active = listImprovementLifecycle(12).filter((item) => item.status !== "verified");
  const explicitTargets =
    record.linkedImprovementIds.length > 0
      ? active.filter((item) => record.linkedImprovementIds.includes(item.id))
      : record.parentOrchestrationId
        ? active.filter(
            (item) =>
              item.dispatchOrchestrationId === record.parentOrchestrationId ||
              item.instructionOrchestrationId === record.parentOrchestrationId
          )
        : [];

  if (explicitTargets.length > 0) {
    const updated: ImprovementRecord[] = [];
    for (const item of explicitTargets) {
      const explicitDispatch = record.parentOrchestrationId
        ? findLatestDispatchRecordByOrchestrationId(record.parentOrchestrationId)
        : null;
      const nextStatus: ImprovementStatus = record.verificationSignal === "verified" ? "verified" : "completed";
      const next = updateImprovementStatus(item.id, nextStatus, {
        instructionOrchestrationId: item.instructionOrchestrationId || record.parentOrchestrationId,
        dispatchRecordId: item.dispatchRecordId || explicitDispatch?.id,
        dispatchOrchestrationId: item.dispatchOrchestrationId || record.parentOrchestrationId,
        dispatchEvidence: item.dispatchEvidence || (record.linkageMode === "explicit" ? "explicit" : "inferred"),
        dispatchedAt: item.dispatchedAt || now(),
        completionOrchestrationId: record.id,
        completionEvidence: record.linkageMode === "explicit" ? "explicit" : "inferred",
        completedAt: now(),
        verificationOrchestrationId: record.verificationSignal === "verified" ? record.id : undefined,
        verificationEvidence: record.verificationSignal === "verified" ? (record.linkageMode === "explicit" ? "explicit" : "inferred") : undefined,
        verifiedAt: record.verificationSignal === "verified" ? now() : undefined
      });
      if (next) {
        updated.push(next);
      }
    }
    return updated;
  }

  const normalized = record.rawOutput.toLowerCase();
  const updated: ImprovementRecord[] = [];
  for (const item of active) {
    const rule = findRule(item.capability);
    if (!rule || !rule.keywords.some((keyword) => normalized.includes(keyword))) {
      continue;
    }

    if (/\b(tests passed|verified|verification passed|build passed|smoke test passed)\b/i.test(record.rawOutput)) {
      const next = updateImprovementStatus(item.id, "verified", {
        completionOrchestrationId: record.id,
        completionEvidence: "inferred",
        completedAt: item.completedAt || now(),
        verificationOrchestrationId: record.id,
        verificationEvidence: "inferred",
        verifiedAt: now()
      });
      if (next) {
        updated.push(next);
      }
      continue;
    }

    if (/\b(implemented|built|added|wired|finished|completed|shipped)\b/i.test(record.rawOutput)) {
      const next = updateImprovementStatus(item.id, "completed", {
        completionOrchestrationId: record.id,
        completionEvidence: "inferred",
        completedAt: now()
      });
      if (next) {
        updated.push(next);
      }
    }
  }

  return updated;
}

export function listImprovementLifecycle(limit = 6): ImprovementRecord[] {
  return listImprovementRows(limit)
    .map(mapImprovementRow)
    .sort(
      (left, right) =>
        (left.status === "verified" ? 1 : 0) - (right.status === "verified" ? 1 : 0) ||
        right.priorityScore - left.priorityScore ||
        right.lastObservedAt.localeCompare(left.lastObservedAt)
    );
}

export function getTopImprovementFocus(): ImprovementRecord | null {
  return getCanonicalTopImprovementFocus();
}

export function getImprovementById(id: string): ImprovementRecord | null {
  const row = getCanonicalCoordinationRecord<ImprovementRow>("self_improvement", id);
  return row ? mapImprovementRow(row) : null;
}

export function getImprovementByDedupeKey(dedupeKey: string): ImprovementRecord | null {
  const row = listImprovementRows(100).find((candidate) => candidate.dedupe_key === dedupeKey);
  return row ? mapImprovementRow(row) : null;
}

export type { ImprovementDraft };
