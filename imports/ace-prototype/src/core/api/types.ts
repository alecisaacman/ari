import type { ApprovalRecord, AriEventRecord, AutonomyLevel } from "@/src/core/agent/activity-types";
import type { ActiveStateSnapshot } from "@/src/core/memory/types";
import type { BuilderOutputRecord, OrchestrationSnapshot } from "@/src/core/orchestration/types";

export type ChatRequestBody = {
  message: string;
  conversationId?: string;
  source?: "web" | "api";
};

export type TriggerRequestBody = {
  text: string;
  conversationId?: string;
  source?: string;
};

export type HealthSnapshot = {
  appName: string;
  mode: "hosted" | "fallback";
  auth: {
    uiPasswordConfigured: boolean;
    triggerTokenConfigured: boolean;
  };
  voice: {
    serverTranscription: boolean;
    serverSpeechSynthesis: boolean;
    browserFallbackInput: boolean;
    browserFallbackOutput: boolean;
  };
  storage: {
    dbReady: boolean;
    workspacePath: string;
  };
  hub: {
    backgroundRuntime: "active";
    orchestrationMode: "manual" | "assisted" | "auto";
    orchestrationPaused: boolean;
    pendingApprovals: number;
    pendingEscalations: number;
  };
};

export type ActiveSessionItem = {
  id: string;
  label: string;
  userAgent: string;
  current: boolean;
  createdAt: string;
  lastSeenAt: string;
};

export type ActivityFeedItem = AriEventRecord;

export type ApprovalQueueItem = ApprovalRecord;

export type ActivitySnapshot = {
  items: ActivityFeedItem[];
  approvals: ApprovalQueueItem[];
  activeState: ActiveStateSnapshot;
  autonomyModel: Array<{
    level: AutonomyLevel;
    title: string;
    description: string;
  }>;
  orchestration: OrchestrationSnapshot;
};

export type OrchestrationRecordItem = BuilderOutputRecord;
