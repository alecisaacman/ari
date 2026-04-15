import path from "node:path";

export type AppMode = "hosted" | "fallback";
export type OrchestrationMode = "manual" | "assisted" | "auto";
export type BuilderConsumerMode = "off" | "polling";

export type AriConfig = {
  appName: string;
  projectRoot: string;
  runtimeRoot: string;
  workspaceRoot: string;
  orchestrationRoot: string;
  orchestrationInboxRoot: string;
  orchestrationProcessedRoot: string;
  orchestrationOutboxRoot: string;
  orchestrationDispatchRoot: string;
  orchestrationDispatchConsumedRoot: string;
  orchestrationDispatchLogPath: string;
  builderConsumerMode: BuilderConsumerMode;
  builderConsumerName: string;
  dbPath: string;
  sessionCookieName: string;
  sessionTtlSeconds: number;
  orchestrationMode: OrchestrationMode;
  uiPassword: string;
  triggerToken: string;
  authSecret: string;
  openAiApiKey: string;
  openAiBaseUrl: string;
  openAiModel: string;
  openAiTranscriptionModel: string;
  openAiTtsModel: string;
  openAiTtsVoice: string;
  canonicalAriProjectRoot: string;
  canonicalAriHome: string;
  canonicalPythonCommand: string;
  executionStallMinutes: number;
};

export function getConfig(): AriConfig {
  const projectRoot = process.cwd();
  const runtimeRoot = path.join(projectRoot, "runtime");
  const workspaceRoot = path.join(projectRoot, "workspace");
  const orchestrationRoot = path.join(runtimeRoot, "orchestration");

  return {
    appName: "ARI",
    projectRoot,
    runtimeRoot,
    workspaceRoot,
    orchestrationRoot,
    orchestrationInboxRoot: path.join(orchestrationRoot, "inbox"),
    orchestrationProcessedRoot: path.join(orchestrationRoot, "processed"),
    orchestrationOutboxRoot: path.join(orchestrationRoot, "outbox"),
    orchestrationDispatchRoot: path.join(orchestrationRoot, "dispatch"),
    orchestrationDispatchConsumedRoot: path.join(orchestrationRoot, "dispatch-consumed"),
    orchestrationDispatchLogPath: path.join(orchestrationRoot, "dispatch-consumer.log"),
    builderConsumerMode: process.env.ARI_BUILDER_CONSUMER_MODE === "off" ? "off" : "polling",
    builderConsumerName: process.env.ARI_BUILDER_CONSUMER_NAME || "ari-builder-consumer",
    dbPath: path.join(runtimeRoot, "ari.db"),
    sessionCookieName: "ari_session",
    sessionTtlSeconds: 60 * 60 * 24 * 7,
    orchestrationMode:
      process.env.ARI_ORCHESTRATION_MODE === "assisted" || process.env.ARI_ORCHESTRATION_MODE === "auto"
        ? process.env.ARI_ORCHESTRATION_MODE
        : "manual",
    uiPassword: process.env.ARI_UI_PASSWORD || "change-me",
    triggerToken: process.env.ARI_TRIGGER_TOKEN || "change-me-too",
    authSecret: process.env.ARI_AUTH_SECRET || "replace-with-a-long-random-secret",
    openAiApiKey: process.env.ARI_OPENAI_API_KEY || "",
    openAiBaseUrl: process.env.ARI_OPENAI_BASE_URL || "https://api.openai.com/v1",
    openAiModel: process.env.ARI_OPENAI_MODEL || "gpt-4.1-mini",
    openAiTranscriptionModel: process.env.ARI_OPENAI_TRANSCRIPTION_MODEL || "gpt-4o-mini-transcribe",
    openAiTtsModel: process.env.ARI_OPENAI_TTS_MODEL || "gpt-4o-mini-tts",
    openAiTtsVoice: process.env.ARI_OPENAI_TTS_VOICE || "alloy",
    canonicalAriProjectRoot: process.env.ARI_CANONICAL_PROJECT_ROOT || path.resolve(projectRoot, "..", ".."),
    canonicalAriHome: process.env.ARI_CANONICAL_HOME || "",
    canonicalPythonCommand: process.env.ARI_CANONICAL_PYTHON || "python3",
    executionStallMinutes: Number.isFinite(Number(process.env.ARI_EXECUTION_STALL_MINUTES))
      ? Math.max(0, Number(process.env.ARI_EXECUTION_STALL_MINUTES))
      : 60
  };
}

export function resolveMode(): AppMode {
  return getConfig().openAiApiKey ? "hosted" : "fallback";
}
