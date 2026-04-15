import type { OrchestrationMode } from "@/src/core/config";

export type OrchestrationRoutingState = "auto_pass" | "auto_summarize" | "escalate_to_alec";
export type DispatchStatus =
  | "paused_for_escalation"
  | "awaiting_alec_send"
  | "awaiting_alec_confirm"
  | "queued_for_auto_dispatch"
  | "auto_dispatch_blocked"
  | "dispatched_to_builder"
  | "auto_dispatched"
  | "consumed_by_builder";

export type EscalationPacket = {
  whyEscalationIsNeeded: string;
  whatChanged: string;
  availableOptions: string[];
  recommendedAction: string;
  exactQuestionForAlec: string;
};

export type BuilderOutputRecord = {
  id: string;
  source: string;
  rawOutput: string;
  status: "pending" | "processed";
  classification?: OrchestrationRoutingState;
  conciseSummary: string;
  nextInstruction: string;
  reasoning: string;
  escalationRequired: boolean;
  escalationPacket?: EscalationPacket;
  alecDecision: string;
  parentOrchestrationId?: string;
  linkedImprovementIds: string[];
  verificationSignal?: "completed" | "verified";
  linkageMode: "explicit" | "heuristic";
  createdAt: string;
  processedAt?: string;
};

export type NextInstructionEnvelope = {
  type: "next_instruction";
  orchestrationId: string;
  linkedImprovementIds: string[];
  mode: OrchestrationMode;
  dispatchStatus: DispatchStatus;
  instruction: string;
  summary: string;
  reasoning: string;
  routingState: OrchestrationRoutingState;
  timestamp: string;
  dispatchedAt?: string;
};

export type BuilderDispatchEnvelope = {
  type: "builder_dispatch";
  dispatchRecordId: string;
  orchestrationId: string;
  linkedImprovementIds: string[];
  mode: OrchestrationMode;
  dispatchStatus: BuilderDispatchRecord["dispatchStatus"];
  instruction: string;
  summary: string;
  reasoning: string;
  routingState: OrchestrationRoutingState;
  timestamp: string;
  dispatchedAt: string;
  trigger: "assisted_confirm" | "auto_policy";
};

export type BuilderConsumedEnvelope = {
  type: "builder_consumed";
  dispatchRecordId: string;
  orchestrationId: string;
  linkedImprovementIds: string[];
  mode: OrchestrationMode;
  dispatchStatus: "consumed_by_builder";
  instruction: string;
  summary: string;
  reasoning: string;
  routingState: OrchestrationRoutingState;
  timestamp: string;
  dispatchedAt: string;
  consumedAt: string;
  consumer: string;
};

export type BuilderDispatchRecord = {
  id: string;
  orchestrationId: string;
  linkedImprovementIds: string[];
  mode: OrchestrationMode;
  instruction: string;
  summary: string;
  reasoning: string;
  routingState: OrchestrationRoutingState;
  dispatchStatus: "dispatched_to_builder" | "auto_dispatched" | "consumed_by_builder";
  trigger: "assisted_confirm" | "auto_policy";
  dispatchedAt: string;
  consumedAt?: string;
  consumer?: string;
  completionOrchestrationId?: string;
  verificationOrchestrationId?: string;
  createdAt: string;
  updatedAt: string;
};

export type OrchestrationSnapshot = {
  control: {
    mode: OrchestrationMode;
    paused: boolean;
    pauseReason: string;
  };
  dispatch: {
    latestStatus: DispatchStatus | "idle";
    latestInstruction: NextInstructionEnvelope | null;
    latestDispatch: BuilderDispatchEnvelope | null;
    latestConsumption: BuilderConsumedEnvelope | null;
    stateLabel: "paused" | "waiting" | "continuing";
  };
  latest: BuilderOutputRecord | null;
  pendingEscalations: BuilderOutputRecord[];
  recent: BuilderOutputRecord[];
};
