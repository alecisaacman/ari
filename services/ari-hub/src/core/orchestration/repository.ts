import { getConfig } from "@/src/core/config";
import { listCanonicalCoordinationRecords, getCanonicalCoordinationRecord, putCanonicalCoordinationRecord } from "@/src/core/ari-spine/coordination-bridge";
import { readLatestConsumedEnvelope, readLatestDispatchEnvelope, readNextInstructionEnvelope } from "@/src/core/orchestration/channels";
import type { BuilderOutputRecord, EscalationPacket, OrchestrationRoutingState, OrchestrationSnapshot } from "@/src/core/orchestration/types";

function now(): string {
  return new Date().toISOString();
}

function parseEscalationPacket(raw: string): EscalationPacket | undefined {
  try {
    const parsed = JSON.parse(raw) as EscalationPacket;
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

function mapRow(row: {
  id: string;
  source: string;
  raw_output: string;
  status: "pending" | "processed";
  classification: OrchestrationRoutingState | null;
  concise_summary: string;
  next_instruction: string;
  reasoning: string;
  escalation_required: number;
  escalation_packet_json: string;
  alec_decision: string;
  parent_orchestration_id: string | null;
  linked_improvement_ids_json: string;
  verification_signal: "completed" | "verified" | null;
  linkage_mode: "explicit" | "heuristic";
  created_at: string;
  processed_at: string | null;
}): BuilderOutputRecord {
  let linkedImprovementIds: string[] = [];
  try {
    const parsed = JSON.parse(row.linked_improvement_ids_json) as string[];
    linkedImprovementIds = Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    linkedImprovementIds = [];
  }

  return {
    id: row.id,
    source: row.source,
    rawOutput: row.raw_output,
    status: row.status,
    classification: row.classification || undefined,
    conciseSummary: row.concise_summary,
    nextInstruction: row.next_instruction,
    reasoning: row.reasoning,
    escalationRequired: Boolean(row.escalation_required),
    escalationPacket: parseEscalationPacket(row.escalation_packet_json),
    alecDecision: row.alec_decision,
    parentOrchestrationId: row.parent_orchestration_id || undefined,
    linkedImprovementIds,
    verificationSignal: row.verification_signal || undefined,
    linkageMode: row.linkage_mode,
    createdAt: row.created_at,
    processedAt: row.processed_at || undefined
  };
}

export function ingestBuilderOutput(input: {
  rawOutput: string;
  source?: string;
  parentOrchestrationId?: string;
  linkedImprovementIds?: string[];
  verificationSignal?: "completed" | "verified";
  linkageMode?: "explicit" | "heuristic";
}): BuilderOutputRecord {
  const record: BuilderOutputRecord = {
    id: crypto.randomUUID(),
    source: input.source || "codex",
    rawOutput: input.rawOutput,
    status: "pending",
    conciseSummary: "",
    nextInstruction: "",
    reasoning: "",
    escalationRequired: false,
    alecDecision: "",
    parentOrchestrationId: input.parentOrchestrationId,
    linkedImprovementIds: input.linkedImprovementIds || [],
    verificationSignal: input.verificationSignal,
    linkageMode: input.linkageMode || "heuristic",
    createdAt: now()
  };

  putCanonicalCoordinationRecord("orchestration_record", {
    id: record.id,
    source: record.source,
    raw_output: record.rawOutput,
    status: record.status,
    classification: null,
    concise_summary: "",
    next_instruction: "",
    reasoning: "",
    escalation_required: 0,
    escalation_packet_json: "{}",
    alec_decision: record.alecDecision,
    parent_orchestration_id: record.parentOrchestrationId || null,
    linked_improvement_ids_json: JSON.stringify(record.linkedImprovementIds),
    verification_signal: record.verificationSignal || null,
    linkage_mode: record.linkageMode,
    created_at: record.createdAt,
    processed_at: null
  });

  return record;
}

export function listPendingBuilderOutputs(limit = 10): BuilderOutputRecord[] {
  const rows = listCanonicalCoordinationRecords<{
    id: string;
    source: string;
    raw_output: string;
    status: "pending" | "processed";
    classification: OrchestrationRoutingState | null;
    concise_summary: string;
    next_instruction: string;
    reasoning: string;
    escalation_required: number;
    escalation_packet_json: string;
    alec_decision: string;
    parent_orchestration_id: string | null;
    linked_improvement_ids_json: string;
    verification_signal: "completed" | "verified" | null;
    linkage_mode: "explicit" | "heuristic";
    created_at: string;
    processed_at: string | null;
  }>("orchestration_record", 100)
    .filter((row) => row.status === "pending")
    .sort((left, right) => left.created_at.localeCompare(right.created_at))
    .slice(0, limit);

  return rows.map(mapRow);
}

export function updateBuilderOutputRecord(
  id: string,
  update: {
    classification: OrchestrationRoutingState;
    conciseSummary: string;
    nextInstruction: string;
    reasoning: string;
    escalationRequired: boolean;
    escalationPacket?: EscalationPacket;
  }
): BuilderOutputRecord {
  const processedAt = now();
  const current = getBuilderOutputRecord(id);
  if (!current) {
    throw new Error(`Builder output record ${id} was not found.`);
  }
  putCanonicalCoordinationRecord("orchestration_record", {
    id: current.id,
    source: current.source,
    raw_output: current.rawOutput,
    status: "processed",
    classification: update.classification,
    concise_summary: update.conciseSummary,
    next_instruction: update.nextInstruction,
    reasoning: update.reasoning,
    escalation_required: update.escalationRequired ? 1 : 0,
    escalation_packet_json: JSON.stringify(update.escalationPacket || {}),
    alec_decision: current.alecDecision,
    parent_orchestration_id: current.parentOrchestrationId || null,
    linked_improvement_ids_json: JSON.stringify(current.linkedImprovementIds),
    verification_signal: current.verificationSignal || null,
    linkage_mode: current.linkageMode,
    created_at: current.createdAt,
    processed_at: processedAt
  });

  return getBuilderOutputRecord(id)!;
}

export function recordAlecDecision(id: string, decision: string): BuilderOutputRecord {
  const current = getBuilderOutputRecord(id);
  if (!current) {
    throw new Error(`Builder output record ${id} was not found.`);
  }
  putCanonicalCoordinationRecord("orchestration_record", {
    id: current.id,
    source: current.source,
    raw_output: current.rawOutput,
    status: current.status,
    classification: current.classification || null,
    concise_summary: current.conciseSummary,
    next_instruction: current.nextInstruction,
    reasoning: current.reasoning,
    escalation_required: current.escalationRequired ? 1 : 0,
    escalation_packet_json: JSON.stringify(current.escalationPacket || {}),
    alec_decision: decision.trim(),
    parent_orchestration_id: current.parentOrchestrationId || null,
    linked_improvement_ids_json: JSON.stringify(current.linkedImprovementIds),
    verification_signal: current.verificationSignal || null,
    linkage_mode: current.linkageMode,
    created_at: current.createdAt,
    processed_at: current.processedAt || null
  });
  return getBuilderOutputRecord(id)!;
}

export function getBuilderOutputRecord(id: string): BuilderOutputRecord | null {
  const row = getCanonicalCoordinationRecord<{
    id: string;
    source: string;
    raw_output: string;
    status: "pending" | "processed";
    classification: OrchestrationRoutingState | null;
    concise_summary: string;
    next_instruction: string;
    reasoning: string;
    escalation_required: number;
    escalation_packet_json: string;
    alec_decision: string;
    parent_orchestration_id: string | null;
    linked_improvement_ids_json: string;
    verification_signal: "completed" | "verified" | null;
    linkage_mode: "explicit" | "heuristic";
    created_at: string;
    processed_at: string | null;
  }>("orchestration_record", id);

  return row ? mapRow(row) : null;
}

export function getOrchestrationSnapshot(limit = 8): OrchestrationSnapshot {
  const config = getConfig();
  const rows = listCanonicalCoordinationRecords<{
    id: string;
    source: string;
    raw_output: string;
    status: "pending" | "processed";
    classification: OrchestrationRoutingState | null;
    concise_summary: string;
    next_instruction: string;
    reasoning: string;
    escalation_required: number;
    escalation_packet_json: string;
    alec_decision: string;
    parent_orchestration_id: string | null;
    linked_improvement_ids_json: string;
    verification_signal: "completed" | "verified" | null;
    linkage_mode: "explicit" | "heuristic";
    created_at: string;
    processed_at: string | null;
  }>("orchestration_record", limit);

  const recent = rows.map(mapRow);
  const pendingEscalations = recent.filter((record) => record.escalationRequired && !record.alecDecision);
  const latestInstruction = readNextInstructionEnvelope();
  const latestDispatch = readLatestDispatchEnvelope();
  const latestConsumption = readLatestConsumedEnvelope();
  const latestStatus = latestConsumption?.dispatchStatus || latestInstruction?.dispatchStatus || latestDispatch?.dispatchStatus || "idle";
  return {
    control: {
      mode: config.orchestrationMode,
      paused: pendingEscalations.length > 0,
      pauseReason: pendingEscalations.length ? "Awaiting Alec on an escalation packet." : ""
    },
    dispatch: {
      latestStatus,
      latestInstruction,
      latestDispatch,
      latestConsumption,
      stateLabel: pendingEscalations.length
        ? "paused"
        : latestStatus === "dispatched_to_builder" || latestStatus === "auto_dispatched" || latestStatus === "consumed_by_builder"
          ? "continuing"
          : "waiting"
    },
    latest: recent[0] || null,
    pendingEscalations,
    recent
  };
}
