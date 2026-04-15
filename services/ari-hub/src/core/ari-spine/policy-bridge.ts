import { isSubprocessBridgeMode, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";
import type {
  AwarenessSnapshot,
  DecisionRecord,
  ImprovementRecord,
  ProjectFocusSnapshot
} from "@/src/core/memory/types";
import type { EscalationPacket, OrchestrationRoutingState } from "@/src/core/orchestration/types";

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
  relativePriority: "highest" | "high" | "medium";
  reflection: {
    repeatedLimitations: number;
    repeatedUserFriction: number;
    repeatedManualSteps: number;
    repeatedEscalationCauses: number;
    total: number;
  };
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

type OrchestrationClassification = {
  classification: OrchestrationRoutingState;
  conciseSummary: string;
  nextInstruction: string;
  reasoning: string;
  escalationRequired: boolean;
  escalationPacket?: EscalationPacket;
};

type ProjectDraft = {
  title: string;
  goal: string;
  completionCriteria: string;
  source: "goal" | "active_project" | "manual";
  milestones: Array<{
    title: string;
    completionCriteria: string;
    steps: Array<{
      title: string;
      completionCriteria: string;
      dependsOnIndexes: number[];
      linkedImprovementId?: string | null;
    }>;
  }>;
};

export function deriveCanonicalAwareness(payload: {
  pendingApprovals: Array<{ id: string; title: string; body: string; createdAt: string }>;
  recentIntent: string[];
  recentDecisions: DecisionRecord[];
}): AwarenessSnapshot {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<AwarenessSnapshot>(["api", "policy", "awareness", "derive", "--payload-json", JSON.stringify(payload)])
    : requestAriApiSync<AwarenessSnapshot>("POST", "/awareness/derive", {
        body: { payload }
      });
}

export function storeCanonicalAwareness(snapshot: AwarenessSnapshot): { snapshot: AwarenessSnapshot; changed: boolean } {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ snapshot: AwarenessSnapshot; changed: boolean }>([
        "api",
        "policy",
        "awareness",
        "store",
        "--payload-json",
        JSON.stringify(snapshot)
      ])
    : requestAriApiSync<{ snapshot: AwarenessSnapshot; changed: boolean }>("POST", "/awareness/store", {
        body: { payload: snapshot }
      });
}

export function getLatestCanonicalAwareness(): AwarenessSnapshot | null {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ snapshot: AwarenessSnapshot | null }>(["api", "policy", "awareness", "latest"])
    : requestAriApiSync<{ snapshot: AwarenessSnapshot | null }>("GET", "/awareness/latest");
  return payload.snapshot;
}

export function classifyCanonicalBuilderOutput(payload: {
  rawOutput: string;
  currentPriority?: string;
  latestDecision?: string;
}): OrchestrationClassification {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<OrchestrationClassification>([
        "api",
        "policy",
        "orchestration-classify",
        "--payload-json",
        JSON.stringify(payload)
      ])
    : requestAriApiSync<OrchestrationClassification>("POST", "/policy/orchestration/classify", {
        body: payload
      });
}

export function detectCanonicalCapabilityGaps(payload: {
  message: string;
  recentMessages: string[];
  taskNotes: string[];
  escalationTexts: string[];
  approvalCounts: Record<string, number>;
}): ImprovementDraft[] {
  const parsed = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ drafts: ImprovementDraft[] }>([
        "api",
        "policy",
        "improvements",
        "detect",
        "--payload-json",
        JSON.stringify(payload)
      ])
    : requestAriApiSync<{ drafts: ImprovementDraft[] }>("POST", "/policy/improvements/detect", {
        body: { payload }
      });
  return parsed.drafts;
}

export function getCanonicalTopImprovementFocus(): ImprovementRecord | null {
  const parsed = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ record: ImprovementRecord | null }>(["api", "policy", "improvements", "focus"])
    : requestAriApiSync<{ record: ImprovementRecord | null }>("GET", "/policy/improvements/focus");
  return parsed.record;
}

export function buildCanonicalProjectDraft(payload: {
  goal: string;
  source: "goal" | "active_project" | "manual";
}): ProjectDraft {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<ProjectDraft>([
        "api",
        "policy",
        "project",
        "draft",
        "--payload-json",
        JSON.stringify(payload)
      ])
    : requestAriApiSync<ProjectDraft>("POST", "/policy/projects/draft", {
        body: payload
      });
}

export function getCanonicalProjectFocus(): ProjectFocusSnapshot | null {
  const parsed = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ focus: ProjectFocusSnapshot | null }>(["api", "policy", "project", "focus"])
    : requestAriApiSync<{ focus: ProjectFocusSnapshot | null }>("GET", "/policy/projects/focus");
  return parsed.focus;
}

export type { ImprovementDraft, OrchestrationClassification, ProjectDraft };
