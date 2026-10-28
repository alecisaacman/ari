import { AUTONOMY_MODEL, listAriEvents, listPendingApprovals, resolveApproval } from "@/src/core/agent/activity";
import { ensureBackgroundRuntime } from "@/src/core/agent/background-runtime";
import {
  approveCanonicalCodingAction,
  createCanonicalCodingAction,
  runCanonicalCodingAction
} from "@/src/core/ari-spine/execution-bridge";
import { getBrainPanel, sendToAri } from "@/src/core/ari-spine/brain-bridge";
import { getConfig } from "@/src/core/config";
import { getDatabase } from "@/src/core/db/database";
import { getActiveStateSnapshot } from "@/src/core/memory/spine";
import { dispatchOrchestrationInstruction, getLatestOrchestrationSnapshot, ingestBuilderOutputForProcessing, recordAlecOrchestrationDecision } from "@/src/core/orchestration/processor";
import type { ChatRequestBody, HealthSnapshot, TriggerRequestBody } from "@/src/core/api/types";

export async function getHealthSnapshot(): Promise<HealthSnapshot> {
  const config = getConfig();

  getDatabase();
  ensureBackgroundRuntime();
  const orchestration = getLatestOrchestrationSnapshot();

  return {
    appName: config.appName,
    // The hub has no model of its own; every message goes to ARI's brain.
    mode: "ari",
    auth: {
      uiPasswordConfigured: Boolean(config.uiPassword && config.uiPassword !== "change-me"),
      triggerTokenConfigured: Boolean(config.triggerToken && config.triggerToken !== "change-me-too")
    },
    voice: {
      serverTranscription: false,
      serverSpeechSynthesis: false,
      browserFallbackInput: true,
      browserFallbackOutput: true
    },
    storage: {
      dbReady: true,
      workspacePath: config.workspaceRoot
    },
    hub: {
      backgroundRuntime: "active",
      orchestrationMode: orchestration.control.mode,
      orchestrationPaused: orchestration.control.paused,
      pendingApprovals: listPendingApprovals().length,
      pendingEscalations: orchestration.pendingEscalations.length
    }
  };
}

export async function getAriPanel() {
  return getBrainPanel();
}

export async function handleChatRequest(body: ChatRequestBody) {
  if (!body.message?.trim()) {
    throw new Error("message is required.");
  }

  return sendToAri(body.message.trim());
}

export async function handleTriggerRequest(body: TriggerRequestBody) {
  if (!body.text?.trim()) {
    throw new Error("text is required.");
  }

  const result = await sendToAri(body.text.trim());
  return {
    reply: result.reply,
    status: "ok"
  };
}

export async function handleVoiceInputRequest(formData: FormData) {
  // Speech is recognized in the browser; ARI hears the transcript like any message.
  const transcriptField = formData.get("transcript");
  const transcript = typeof transcriptField === "string" ? transcriptField.trim() : "";
  if (!transcript) {
    throw new Error("transcript is required. Use the browser's speech recognition.");
  }

  const result = await sendToAri(transcript);
  return {
    transcript,
    reply: result.reply,
    conversation: result.conversation
  };
}

export async function getActivitySnapshot() {
  ensureBackgroundRuntime();
  const orchestration = getLatestOrchestrationSnapshot();
  return {
    items: listAriEvents(),
    approvals: listPendingApprovals(),
    activeState: getActiveStateSnapshot(),
    autonomyModel: [...AUTONOMY_MODEL],
    orchestration
  };
}

export async function handleApprovalDecision(approvalId: string, decision: "approve" | "deny") {
  ensureBackgroundRuntime();
  const approval = await resolveApproval(approvalId, decision);
  return {
    ok: true,
    approval
  };
}

export async function handleBuilderOutputIngest(rawOutput: string, source = "codex") {
  if (!rawOutput.trim()) {
    throw new Error("rawOutput is required.");
  }

  ensureBackgroundRuntime();
  const record = ingestBuilderOutputForProcessing(rawOutput, source);
  return {
    ok: true,
    record
  };
}

export async function getOrchestrationSnapshot() {
  ensureBackgroundRuntime();
  return getLatestOrchestrationSnapshot();
}

export async function handleAlecDecision(recordId: string, decision: string) {
  if (!decision.trim()) {
    throw new Error("decision is required.");
  }

  ensureBackgroundRuntime();
  return {
    ok: true,
    record: recordAlecOrchestrationDecision(recordId, decision)
  };
}

export async function handleOrchestrationDispatch(recordId: string) {
  ensureBackgroundRuntime();
  return {
    ok: true,
    ...dispatchOrchestrationInstruction(recordId)
  };
}

export async function handleCodingActionCreate(payload: {
  title: string;
  summary?: string;
  operations: Array<{ type: "write" | "patch"; path: string; content?: string; find?: string; replace?: string }>;
  verifyCommand?: string;
  workingDirectory?: string;
  approvalRequired?: boolean | null;
}) {
  ensureBackgroundRuntime();
  return {
    ok: true,
    action: await createCanonicalCodingAction(payload)
  };
}

export async function handleCodingActionApprove(actionId: string) {
  ensureBackgroundRuntime();
  return {
    ok: true,
    action: await approveCanonicalCodingAction(actionId)
  };
}

export async function handleCodingActionRun(actionId: string) {
  ensureBackgroundRuntime();
  return {
    ok: true,
    ...(await runCanonicalCodingAction(actionId))
  };
}
