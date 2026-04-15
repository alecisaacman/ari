import fs from "node:fs";
import path from "node:path";

import { getConfig, type OrchestrationMode } from "@/src/core/config";
import { recordDispatchConsumption, recordDispatchEnvelope } from "@/src/core/orchestration/dispatch-records";
import type {
  BuilderDispatchEnvelope,
  BuilderConsumedEnvelope,
  BuilderOutputRecord,
  DispatchStatus,
  NextInstructionEnvelope,
  OrchestrationRoutingState
} from "@/src/core/orchestration/types";

type BuilderDropPayload = {
  rawOutput: string;
  source: string;
  filename: string;
  parentOrchestrationId?: string;
  linkedImprovementIds: string[];
  verificationSignal?: "completed" | "verified";
  linkageMode: "explicit" | "heuristic";
};

function now(): string {
  return new Date().toISOString();
}

function readBuilderDropPayload(filePath: string, filename: string): BuilderDropPayload | null {
  const raw = fs.readFileSync(filePath, "utf8").trim();
  if (!raw) {
    return null;
  }

  if (path.extname(filename).toLowerCase() === ".json") {
    try {
      const parsed = JSON.parse(raw) as {
        rawOutput?: string;
        source?: string;
        parentOrchestrationId?: string;
        linkedImprovementIds?: string[];
        verificationSignal?: string;
      };
      const rawOutput = typeof parsed.rawOutput === "string" ? parsed.rawOutput.trim() : "";
      if (!rawOutput) {
        return null;
      }

      return {
        rawOutput,
        source: typeof parsed.source === "string" && parsed.source.trim() ? parsed.source.trim() : "codex",
        filename,
        parentOrchestrationId:
          typeof parsed.parentOrchestrationId === "string" && parsed.parentOrchestrationId.trim()
            ? parsed.parentOrchestrationId.trim()
            : undefined,
        linkedImprovementIds: Array.isArray(parsed.linkedImprovementIds)
          ? parsed.linkedImprovementIds.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          : [],
        verificationSignal:
          parsed.verificationSignal === "completed" || parsed.verificationSignal === "verified"
            ? parsed.verificationSignal
            : undefined,
        linkageMode: "explicit"
      };
    } catch {
      return {
        rawOutput: raw,
        source: "codex",
        filename,
        linkedImprovementIds: [],
        linkageMode: "heuristic"
      };
    }
  }

  return {
    rawOutput: raw,
    source: "codex",
    filename,
    linkedImprovementIds: [],
    linkageMode: "heuristic"
  };
}

function archiveBuilderDrop(filePath: string, filename: string): void {
  const config = getConfig();
  fs.mkdirSync(config.orchestrationProcessedRoot, { recursive: true });
  const archivedName = `${new Date().toISOString().replace(/[:.]/g, "-")}--${filename}`;
  fs.renameSync(filePath, path.join(config.orchestrationProcessedRoot, archivedName));
}

export function pullBuilderOutputDropFiles(): BuilderDropPayload[] {
  const config = getConfig();
  fs.mkdirSync(config.orchestrationInboxRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationProcessedRoot, { recursive: true });
  const filenames = fs
    .readdirSync(config.orchestrationInboxRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();

  const payloads: BuilderDropPayload[] = [];

  for (const filename of filenames) {
    const filePath = path.join(config.orchestrationInboxRoot, filename);
    const payload = readBuilderDropPayload(filePath, filename);
    archiveBuilderDrop(filePath, filename);
    if (payload) {
      payloads.push(payload);
    }
  }

  return payloads;
}

function writeJsonFile(filePath: string, value: unknown): void {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function readJsonFile<T>(filePath: string): T | null {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

function initialDispatchStatus(
  mode: OrchestrationMode,
  paused: boolean,
  routingState: OrchestrationRoutingState
): DispatchStatus {
  if (paused) {
    return "paused_for_escalation";
  }
  if (mode === "manual") {
    return "awaiting_alec_send";
  }
  if (mode === "assisted") {
    return "awaiting_alec_confirm";
  }
  return routingState === "auto_pass" ? "queued_for_auto_dispatch" : "auto_dispatch_blocked";
}

function buildNextInstructionEnvelope(
  record: BuilderOutputRecord,
  mode: OrchestrationMode,
  paused: boolean,
  dispatchStatus?: DispatchStatus,
  dispatchedAt?: string
): NextInstructionEnvelope {
  return {
    type: "next_instruction",
    orchestrationId: record.id,
    linkedImprovementIds: record.linkedImprovementIds,
    mode,
    dispatchStatus: dispatchStatus || initialDispatchStatus(mode, paused, record.classification || "auto_pass"),
    instruction: paused ? "" : record.nextInstruction,
    summary: record.conciseSummary,
    reasoning: record.reasoning,
    routingState: record.classification || "auto_pass",
    timestamp: now(),
    dispatchedAt
  };
}

function writeNextInstructionEnvelope(record: BuilderOutputRecord, envelope: NextInstructionEnvelope): void {
  const config = getConfig();
  fs.mkdirSync(config.orchestrationOutboxRoot, { recursive: true });
  writeJsonFile(path.join(config.orchestrationOutboxRoot, "latest-next-instruction.json"), envelope);
  writeJsonFile(path.join(config.orchestrationOutboxRoot, `next-instruction-${record.id}.json`), envelope);
}

export function emitNextInstructionChannel(record: BuilderOutputRecord, mode: OrchestrationMode, paused: boolean): void {
  writeNextInstructionEnvelope(record, buildNextInstructionEnvelope(record, mode, paused));
}

export function emitEscalationChannel(record: BuilderOutputRecord, mode: OrchestrationMode): void {
  const config = getConfig();
  fs.mkdirSync(config.orchestrationOutboxRoot, { recursive: true });
  const envelope = {
    type: "escalation_packet",
    orchestrationId: record.id,
    mode,
    summary: record.conciseSummary,
    reasoning: record.reasoning,
    escalationPacket: record.escalationPacket || null,
    timestamp: now()
  };

  writeJsonFile(path.join(config.orchestrationOutboxRoot, "latest-escalation.json"), envelope);
  writeJsonFile(path.join(config.orchestrationOutboxRoot, `escalation-${record.id}.json`), envelope);
}

export function readNextInstructionEnvelope(orchestrationId?: string): NextInstructionEnvelope | null {
  const config = getConfig();
  const filename = orchestrationId ? `next-instruction-${orchestrationId}.json` : "latest-next-instruction.json";
  return readJsonFile<NextInstructionEnvelope>(path.join(config.orchestrationOutboxRoot, filename));
}

export function readLatestDispatchEnvelope(): BuilderDispatchEnvelope | null {
  const config = getConfig();
  return readJsonFile<BuilderDispatchEnvelope>(path.join(config.orchestrationDispatchRoot, "latest-dispatch.json"));
}

export function readLatestConsumedEnvelope(): BuilderConsumedEnvelope | null {
  const config = getConfig();
  return readJsonFile<BuilderConsumedEnvelope>(path.join(config.orchestrationDispatchConsumedRoot, "latest-consumed.json"));
}

export function dispatchNextInstruction(record: BuilderOutputRecord, mode: OrchestrationMode, trigger: "assisted_confirm" | "auto_policy"): BuilderDispatchEnvelope {
  const config = getConfig();
  fs.mkdirSync(config.orchestrationDispatchRoot, { recursive: true });
  const nextInstruction = readNextInstructionEnvelope(record.id) || buildNextInstructionEnvelope(record, mode, false);
  const dispatchedAt = now();
  const dispatchStatus: DispatchStatus = trigger === "auto_policy" ? "auto_dispatched" : "dispatched_to_builder";
  const dispatchEnvelope: BuilderDispatchEnvelope = {
    type: "builder_dispatch",
    dispatchRecordId: crypto.randomUUID(),
    orchestrationId: record.id,
    linkedImprovementIds: nextInstruction.linkedImprovementIds || [],
    mode,
    dispatchStatus,
    instruction: nextInstruction.instruction,
    summary: nextInstruction.summary,
    reasoning: nextInstruction.reasoning,
    routingState: nextInstruction.routingState,
    timestamp: now(),
    dispatchedAt,
    trigger
  };

  writeJsonFile(path.join(config.orchestrationDispatchRoot, "latest-dispatch.json"), dispatchEnvelope);
  writeJsonFile(path.join(config.orchestrationDispatchRoot, `dispatch-${record.id}.json`), dispatchEnvelope);
  recordDispatchEnvelope(dispatchEnvelope);
  writeNextInstructionEnvelope(
    record,
    buildNextInstructionEnvelope(record, mode, false, dispatchStatus, dispatchedAt)
  );

  return dispatchEnvelope;
}

export function consumeLatestDispatch(consumer = "local-builder"): BuilderConsumedEnvelope | null {
  const config = getConfig();
  const latestDispatch = readLatestDispatchEnvelope();
  if (!latestDispatch) {
    return null;
  }

  fs.mkdirSync(config.orchestrationDispatchConsumedRoot, { recursive: true });
  const consumedPath = path.join(config.orchestrationDispatchConsumedRoot, `consumed-${latestDispatch.orchestrationId}.json`);
  if (fs.existsSync(consumedPath)) {
    return readJsonFile<BuilderConsumedEnvelope>(consumedPath);
  }

  const consumedAt = now();
  const envelope: BuilderConsumedEnvelope = {
    type: "builder_consumed",
    dispatchRecordId: latestDispatch.dispatchRecordId,
    orchestrationId: latestDispatch.orchestrationId,
    linkedImprovementIds: latestDispatch.linkedImprovementIds || [],
    mode: latestDispatch.mode,
    dispatchStatus: "consumed_by_builder",
    instruction: latestDispatch.instruction,
    summary: latestDispatch.summary,
    reasoning: latestDispatch.reasoning,
    routingState: latestDispatch.routingState,
    timestamp: now(),
    dispatchedAt: latestDispatch.dispatchedAt,
    consumedAt,
    consumer
  };

  writeJsonFile(path.join(config.orchestrationDispatchConsumedRoot, "latest-consumed.json"), envelope);
  writeJsonFile(consumedPath, envelope);
  recordDispatchConsumption(envelope);
  fs.appendFileSync(
    config.orchestrationDispatchLogPath,
    `[${consumedAt}] ${consumer} consumed ${latestDispatch.orchestrationId}\n`,
    "utf8"
  );
  return envelope;
}
