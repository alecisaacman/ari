import { recordAriEvent } from "@/src/core/agent/activity";
import {
  markImprovementConsumedFromDispatch,
  markImprovementDispatchedFromInstruction,
  markImprovementLinkedToInstruction,
  markImprovementProgressFromBuilderOutput
} from "@/src/core/agent/self-improvement";
import { markDispatchRecordBuilderProgress } from "@/src/core/orchestration/dispatch-records";
import { getActiveStateSnapshot, rememberOperatorDecision } from "@/src/core/memory/spine";
import {
  consumeLatestDispatch,
  dispatchNextInstruction,
  emitEscalationChannel,
  emitNextInstructionChannel,
  pullBuilderOutputDropFiles,
  readLatestConsumedEnvelope
} from "@/src/core/orchestration/channels";
import { classifyBuilderOutput } from "@/src/core/orchestration/classifier";
import { getOrchestrationSnapshot, ingestBuilderOutput, listPendingBuilderOutputs, recordAlecDecision, updateBuilderOutputRecord } from "@/src/core/orchestration/repository";
import type { BuilderOutputRecord } from "@/src/core/orchestration/types";

function shouldAutoDispatch(record: BuilderOutputRecord, mode: "manual" | "assisted" | "auto"): boolean {
  return mode === "auto" && !record.escalationRequired && record.classification === "auto_pass" && Boolean(record.nextInstruction.trim());
}

export function ingestBuilderOutputForProcessing(
  rawOutput: string,
  source = "codex",
  options: {
    parentOrchestrationId?: string;
    linkedImprovementIds?: string[];
    verificationSignal?: "completed" | "verified";
    linkageMode?: "explicit" | "heuristic";
  } = {}
): BuilderOutputRecord {
  const record = ingestBuilderOutput({
    rawOutput,
    source,
    parentOrchestrationId: options.parentOrchestrationId,
    linkedImprovementIds: options.linkedImprovementIds,
    verificationSignal: options.verificationSignal,
    linkageMode: options.linkageMode
  });
  recordAriEvent({
    type: "orchestration_received",
    title: "Builder output received",
    body: `ARI queued new builder output from ${source}.`,
    autonomyLevel: "report",
    metadata: { orchestrationId: record.id, source }
  });
  return record;
}

export function ingestBuilderOutputsFromChannel(): BuilderOutputRecord[] {
  return pullBuilderOutputDropFiles().map((payload) =>
    ingestBuilderOutputForProcessing(payload.rawOutput, payload.source, {
      parentOrchestrationId: payload.parentOrchestrationId,
      linkedImprovementIds: payload.linkedImprovementIds,
      verificationSignal: payload.verificationSignal,
      linkageMode: payload.linkageMode
    })
  );
}

export async function processPendingBuilderOutputs(limit = 4): Promise<BuilderOutputRecord[]> {
  const snapshot = getOrchestrationSnapshot();
  if (snapshot.control.paused) {
    return [];
  }

  let pending = listPendingBuilderOutputs(limit);
  if (
    snapshot.dispatch.latestDispatch &&
    (snapshot.dispatch.latestDispatch.dispatchStatus === "dispatched_to_builder" ||
      snapshot.dispatch.latestDispatch.dispatchStatus === "auto_dispatched")
  ) {
    pending = pending.filter((record) => record.createdAt > snapshot.dispatch.latestDispatch!.dispatchedAt);
    if (!pending.length) {
      return [];
    }
  }

  const processed: BuilderOutputRecord[] = [];

  for (const record of pending) {
    const improved = markImprovementProgressFromBuilderOutput({
      id: record.id,
      rawOutput: record.rawOutput,
      parentOrchestrationId: record.parentOrchestrationId,
      linkedImprovementIds: record.linkedImprovementIds,
      verificationSignal: record.verificationSignal,
      linkageMode: record.linkageMode
    });
    markDispatchRecordBuilderProgress({
      recordId: record.id,
      parentOrchestrationId: record.parentOrchestrationId,
      verificationSignal: record.verificationSignal
    });
    for (const item of improved) {
      recordAriEvent({
        type: "observation_generated",
        title: `Self-improvement ${item.status}`,
        body: `${item.missingCapability} is now ${item.status}.`,
        autonomyLevel: "report",
        metadata: { improvementId: item.id, capability: item.capability, status: item.status }
      });
    }

    const state = getActiveStateSnapshot();
    const classification = classifyBuilderOutput(record.rawOutput, {
      currentPriority: state.currentPriorities[0]?.content,
      latestDecision: state.recentDecisions[0]?.body
    });

    recordAriEvent({
      type: "orchestration_classified",
      title: `Builder output classified as ${classification.classification}`,
      body: classification.reasoning,
      autonomyLevel: classification.escalationRequired ? "propose" : "report",
      metadata: { orchestrationId: record.id, classification: classification.classification }
    });

    recordAriEvent({
      type: "orchestration_summary_generated",
      title: "ARI generated a builder summary",
      body: classification.conciseSummary,
      autonomyLevel: "report",
      metadata: { orchestrationId: record.id }
    });

    const updated = updateBuilderOutputRecord(record.id, {
      classification: classification.classification,
      conciseSummary: classification.conciseSummary,
      nextInstruction: classification.nextInstruction,
      reasoning: classification.reasoning,
      escalationRequired: classification.escalationRequired,
      escalationPacket: classification.escalationPacket
    });

    if (classification.escalationRequired) {
      recordAriEvent({
        type: "orchestration_escalation_requested",
        title: "ARI is escalating to Alec",
        body: classification.escalationPacket?.exactQuestionForAlec || "Operator input is required.",
        autonomyLevel: "propose",
        metadata: { orchestrationId: record.id }
      });
      emitEscalationChannel(updated, snapshot.control.mode);
      emitNextInstructionChannel(updated, snapshot.control.mode, true);
      processed.push(updated);
      break;
    } else if (classification.nextInstruction) {
      recordAriEvent({
        type: "orchestration_next_instruction",
        title: "ARI generated the next builder instruction",
        body: classification.nextInstruction,
        autonomyLevel: "execute",
        metadata: { orchestrationId: record.id }
      });
      emitNextInstructionChannel(updated, snapshot.control.mode, false);
      if (shouldAutoDispatch(updated, snapshot.control.mode)) {
        const dispatched = dispatchNextInstruction(updated, snapshot.control.mode, "auto_policy");
        const progressed =
          updated.linkedImprovementIds.length > 0
            ? markImprovementLinkedToInstruction(
                updated.id,
                snapshot.control.mode,
                updated.linkedImprovementIds,
                "explicit",
                dispatched.dispatchRecordId
              )
            : markImprovementDispatchedFromInstruction(updated.nextInstruction);
        recordAriEvent({
          type: "action_executed",
          title: "Builder instruction dispatched",
          body: `ARI dispatched the next instruction automatically through the local builder channel (${dispatched.dispatchStatus}).`,
          autonomyLevel: "execute",
          metadata: { orchestrationId: record.id, dispatchStatus: dispatched.dispatchStatus }
        });
        for (const item of progressed) {
          recordAriEvent({
            type: "observation_generated",
            title: `Self-improvement dispatched`,
            body: `${item.missingCapability} moved into builder dispatch.`,
            autonomyLevel: "report",
            metadata: { improvementId: item.id, capability: item.capability, status: item.status }
          });
        }
        processed.push(updated);
        break;
      }
    }

    processed.push(updated);
  }

  return processed;
}

export function getLatestOrchestrationSnapshot() {
  const latestConsumption = readLatestConsumedEnvelope();
  if (latestConsumption) {
    markImprovementConsumedFromDispatch(latestConsumption.dispatchRecordId, latestConsumption.consumer);
  }
  return getOrchestrationSnapshot();
}

export function recordAlecOrchestrationDecision(recordId: string, decision: string) {
  const updated = recordAlecDecision(recordId, decision);
  rememberOperatorDecision(updated.conciseSummary || "Alec decision recorded", decision, ["orchestration", "alec"]);
  recordAriEvent({
    type: "orchestration_summary_generated",
    title: "Alec decision recorded",
    body: decision,
    autonomyLevel: "report",
    metadata: { orchestrationId: recordId }
  });
  return updated;
}

export function dispatchOrchestrationInstruction(recordId: string) {
  const snapshot = getOrchestrationSnapshot();
  if (snapshot.control.paused) {
    throw new Error("Dispatch is paused until Alec resolves the current escalation.");
  }

  if (snapshot.control.mode !== "assisted") {
    throw new Error("Manual mode expects Alec to relay. Auto mode dispatches on its own when policy allows.");
  }

  const record = snapshot.recent.find((item) => item.id === recordId) || listPendingBuilderOutputs(20).find((item) => item.id === recordId);
  if (!record) {
    throw new Error("Orchestration record was not found.");
  }

  if (!record.nextInstruction.trim()) {
    throw new Error("No builder instruction is available for dispatch.");
  }

  if (
    snapshot.dispatch.latestInstruction?.orchestrationId === recordId &&
    (snapshot.dispatch.latestInstruction.dispatchStatus === "dispatched_to_builder" ||
      snapshot.dispatch.latestInstruction.dispatchStatus === "auto_dispatched")
  ) {
    throw new Error("This builder instruction has already been dispatched.");
  }

  const dispatched = dispatchNextInstruction(record, snapshot.control.mode, "assisted_confirm");
  const progressed =
    record.linkedImprovementIds.length > 0
      ? markImprovementLinkedToInstruction(
          record.id,
          snapshot.control.mode,
          record.linkedImprovementIds,
          "explicit",
          dispatched.dispatchRecordId
        )
      : markImprovementDispatchedFromInstruction(record.nextInstruction);
  recordAriEvent({
    type: "action_executed",
    title: "Builder instruction dispatched",
    body: "Alec confirmed the handoff and ARI wrote the next instruction into the local builder dispatch channel.",
    autonomyLevel: "execute",
    metadata: { orchestrationId: record.id, dispatchStatus: dispatched.dispatchStatus }
  });
  for (const item of progressed) {
    recordAriEvent({
      type: "observation_generated",
      title: `Self-improvement dispatched`,
      body: `${item.missingCapability} moved into builder dispatch.`,
      autonomyLevel: "report",
      metadata: { improvementId: item.id, capability: item.capability, status: item.status }
    });
  }

  return {
    record,
    dispatch: dispatched
  };
}

export function consumeOrchestrationDispatch(consumer = "local-builder") {
  const consumed = consumeLatestDispatch(consumer);
  if (!consumed) {
    throw new Error("No dispatched builder instruction is available to consume.");
  }

  const progressed = markImprovementConsumedFromDispatch(consumed.dispatchRecordId, consumed.consumer);
  for (const item of progressed) {
    recordAriEvent({
      type: "observation_generated",
      title: "Self-improvement picked up",
      body: `${item.missingCapability} has been picked up by ${consumed.consumer}.`,
      autonomyLevel: "report",
      metadata: { improvementId: item.id, capability: item.capability, consumer: consumed.consumer }
    });
  }

  return consumed;
}
