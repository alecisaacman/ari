import {
  getCanonicalCoordinationRecord,
  listCanonicalCoordinationRecords,
  putCanonicalCoordinationRecord
} from "@/src/core/ari-spine/coordination-bridge";
import type { BuilderConsumedEnvelope, BuilderDispatchEnvelope, BuilderDispatchRecord } from "@/src/core/orchestration/types";

type DispatchRow = {
  id: string;
  orchestration_id: string;
  linked_improvement_ids_json: string;
  mode: "manual" | "assisted" | "auto";
  instruction: string;
  summary: string;
  reasoning: string;
  routing_state: "auto_pass" | "auto_summarize" | "escalate_to_alec";
  dispatch_status: "dispatched_to_builder" | "auto_dispatched" | "consumed_by_builder";
  trigger: "assisted_confirm" | "auto_policy";
  dispatched_at: string;
  consumed_at: string | null;
  consumer: string | null;
  completion_orchestration_id: string | null;
  verification_orchestration_id: string | null;
  created_at: string;
  updated_at: string;
};

function now(): string {
  return new Date().toISOString();
}

function parseLinked(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw) as string[];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function mapRow(row: DispatchRow): BuilderDispatchRecord {
  return {
    id: row.id,
    orchestrationId: row.orchestration_id,
    linkedImprovementIds: parseLinked(row.linked_improvement_ids_json),
    mode: row.mode,
    instruction: row.instruction,
    summary: row.summary,
    reasoning: row.reasoning,
    routingState: row.routing_state,
    dispatchStatus: row.dispatch_status,
    trigger: row.trigger,
    dispatchedAt: row.dispatched_at,
    consumedAt: row.consumed_at || undefined,
    consumer: row.consumer || undefined,
    completionOrchestrationId: row.completion_orchestration_id || undefined,
    verificationOrchestrationId: row.verification_orchestration_id || undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

export function recordDispatchEnvelope(envelope: BuilderDispatchEnvelope): BuilderDispatchRecord {
  const timestamp = now();
  putCanonicalCoordinationRecord<DispatchRow>("dispatch_record", {
    id: envelope.dispatchRecordId,
    orchestration_id: envelope.orchestrationId,
    linked_improvement_ids_json: JSON.stringify(envelope.linkedImprovementIds || []),
    mode: envelope.mode,
    instruction: envelope.instruction,
    summary: envelope.summary,
    reasoning: envelope.reasoning,
    routing_state: envelope.routingState,
    dispatch_status: envelope.dispatchStatus,
    trigger: envelope.trigger,
    dispatched_at: envelope.dispatchedAt,
    consumed_at: null,
    consumer: null,
    completion_orchestration_id: null,
    verification_orchestration_id: null,
    created_at: timestamp,
    updated_at: timestamp
  });

  return getDispatchRecord(envelope.dispatchRecordId)!;
}

export function recordDispatchConsumption(envelope: BuilderConsumedEnvelope): BuilderDispatchRecord | null {
  const current = getDispatchRecord(envelope.dispatchRecordId);
  if (!current) {
    return null;
  }
  putCanonicalCoordinationRecord<DispatchRow>("dispatch_record", {
    ...toDispatchRow(current),
    dispatch_status: envelope.dispatchStatus,
    consumed_at: envelope.consumedAt,
    consumer: envelope.consumer,
    updated_at: now()
  });
  return getDispatchRecord(envelope.dispatchRecordId);
}

export function markDispatchRecordBuilderProgress(input: {
  recordId: string;
  parentOrchestrationId?: string;
  verificationSignal?: "completed" | "verified";
}): BuilderDispatchRecord[] {
  if (!input.parentOrchestrationId) {
    return [];
  }

  const rows = listCanonicalCoordinationRecords<DispatchRow>("dispatch_record", 100).filter(
    (row) => row.orchestration_id === input.parentOrchestrationId
  );

  if (!rows.length) {
    return [];
  }

  for (const row of rows) {
    putCanonicalCoordinationRecord<DispatchRow>("dispatch_record", {
      ...row,
      completion_orchestration_id: input.recordId || row.completion_orchestration_id,
      verification_orchestration_id:
        input.verificationSignal === "verified" ? input.recordId : row.verification_orchestration_id,
      updated_at: now()
    });
  }

  return rows.map((row) => getDispatchRecord(row.id)!).filter(Boolean);
}

export function getDispatchRecord(id: string): BuilderDispatchRecord | null {
  const row = getCanonicalCoordinationRecord<DispatchRow>("dispatch_record", id);
  return row ? mapRow(row) : null;
}

export function findLatestDispatchRecordByOrchestrationId(orchestrationId: string): BuilderDispatchRecord | null {
  const row = listCanonicalCoordinationRecords<DispatchRow>("dispatch_record", 100).find(
    (record) => record.orchestration_id === orchestrationId
  );

  return row ? mapRow(row) : null;
}

export function listRecentDispatchRecords(limit = 8): BuilderDispatchRecord[] {
  return listCanonicalCoordinationRecords<DispatchRow>("dispatch_record", limit).map(mapRow);
}

function toDispatchRow(record: BuilderDispatchRecord): DispatchRow {
  return {
    id: record.id,
    orchestration_id: record.orchestrationId,
    linked_improvement_ids_json: JSON.stringify(record.linkedImprovementIds || []),
    mode: record.mode,
    instruction: record.instruction,
    summary: record.summary,
    reasoning: record.reasoning,
    routing_state: record.routingState,
    dispatch_status: record.dispatchStatus,
    trigger: record.trigger,
    dispatched_at: record.dispatchedAt,
    consumed_at: record.consumedAt || null,
    consumer: record.consumer || null,
    completion_orchestration_id: record.completionOrchestrationId || null,
    verification_orchestration_id: record.verificationOrchestrationId || null,
    created_at: record.createdAt,
    updated_at: record.updatedAt
  };
}
