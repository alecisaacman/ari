import { AUTONOMY_MODEL, listAriEvents, listPendingApprovals, resolveApproval } from "@/src/core/agent/activity";
import { ensureBackgroundRuntime } from "@/src/core/agent/background-runtime";
import { getConfig } from "@/src/core/config";
import { getDatabase } from "@/src/core/db/database";
import { runTurn } from "@/src/core/agent/run-turn";
import { getActiveStateSnapshot } from "@/src/core/memory/spine";
import { getModelProvider } from "@/src/core/models";
import { dispatchOrchestrationInstruction, getLatestOrchestrationSnapshot, ingestBuilderOutputForProcessing, recordAlecOrchestrationDecision } from "@/src/core/orchestration/processor";
import { getVoiceCapabilities } from "@/src/core/voice/capabilities";
import type { ChatRequestBody, HealthSnapshot, TriggerRequestBody } from "@/src/core/api/types";

export async function getHealthSnapshot(): Promise<HealthSnapshot> {
  const config = getConfig();
  const provider = getModelProvider();
  const voice = getVoiceCapabilities();

  getDatabase();
  ensureBackgroundRuntime();
  const orchestration = getLatestOrchestrationSnapshot();

  return {
    appName: config.appName,
    mode: provider.mode,
    auth: {
      uiPasswordConfigured: Boolean(config.uiPassword && config.uiPassword !== "change-me"),
      triggerTokenConfigured: Boolean(config.triggerToken && config.triggerToken !== "change-me-too")
    },
    voice,
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

export async function handleChatRequest(body: ChatRequestBody) {
  if (!body.message?.trim()) {
    throw new Error("message is required.");
  }

  ensureBackgroundRuntime();
  return runTurn({
    message: body.message,
    conversationId: body.conversationId,
    source: body.source || "web"
  });
}

export async function handleTriggerRequest(body: TriggerRequestBody) {
  if (!body.text?.trim()) {
    throw new Error("text is required.");
  }

  ensureBackgroundRuntime();
  const result = await runTurn({
    message: body.text,
    conversationId: body.conversationId,
    source: body.source || "trigger"
  });

  return {
    reply: result.reply,
    conversationId: result.conversationId,
    status: result.mode === "hosted" ? "ok" : "fallback"
  };
}

export async function handleVoiceInputRequest(formData: FormData) {
  const provider = getModelProvider();
  const transcriptField = formData.get("transcript");
  const conversationId = typeof formData.get("conversationId") === "string" ? String(formData.get("conversationId")) : undefined;
  ensureBackgroundRuntime();

  let transcript = typeof transcriptField === "string" ? transcriptField.trim() : "";

  if (!transcript) {
    const file = formData.get("file");
    if (!(file instanceof File)) {
      throw new Error("file is required.");
    }

    if (!provider.supportsTranscription) {
      return {
        transcript: "",
        conversationId: conversationId || "",
        reply: "Server transcription is unavailable. Use browser speech recognition and then send the transcript through chat.",
        mode: provider.mode,
        requiresBrowserTranscription: true
      };
    }

    const transcription = await provider.transcribeAudio(file);
    transcript = transcription.transcript;
  }

  const result = await runTurn({
    message: transcript,
    conversationId,
    source: "voice"
  });

  return {
    transcript,
    conversationId: result.conversationId,
    reply: result.reply,
    mode: result.mode
  };
}

export async function handleVoiceOutputRequest(text: string) {
  const provider = getModelProvider();
  if (!text.trim()) {
    throw new Error("text is required.");
  }

  ensureBackgroundRuntime();

  if (!provider.supportsSpeechSynthesis) {
    return {
      mode: provider.mode,
      useBrowserTts: true
    };
  }

  return provider.synthesizeSpeech(text);
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
