import { execFileSync } from "node:child_process";

import { getConfig } from "@/src/core/config";
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

function buildCommandEnvironment(): NodeJS.ProcessEnv {
  const config = getConfig();
  return {
    ...process.env,
    PYTHONPATH: "src",
    ...(config.canonicalAriHome ? { ARI_HOME: config.canonicalAriHome } : {})
  };
}

function runCanonicalCommand(args: string[]): string {
  const config = getConfig();
  return execFileSync(config.canonicalPythonCommand, ["-m", "networking_crm.ari", ...args], {
    cwd: config.canonicalAriProjectRoot,
    env: buildCommandEnvironment(),
    encoding: "utf8"
  }).trim();
}

export function deriveCanonicalAwareness(payload: {
  pendingApprovals: Array<{ id: string; title: string; body: string; createdAt: string }>;
  recentIntent: string[];
  recentDecisions: DecisionRecord[];
}): AwarenessSnapshot {
  const stdout = runCanonicalCommand(["api", "policy", "awareness", "derive", "--payload-json", JSON.stringify(payload)]);
  return JSON.parse(stdout) as AwarenessSnapshot;
}

export function storeCanonicalAwareness(snapshot: AwarenessSnapshot): { snapshot: AwarenessSnapshot; changed: boolean } {
  const stdout = runCanonicalCommand(["api", "policy", "awareness", "store", "--payload-json", JSON.stringify(snapshot)]);
  return JSON.parse(stdout) as { snapshot: AwarenessSnapshot; changed: boolean };
}

export function getLatestCanonicalAwareness(): AwarenessSnapshot | null {
  const stdout = runCanonicalCommand(["api", "policy", "awareness", "latest"]);
  const payload = JSON.parse(stdout) as { snapshot: AwarenessSnapshot | null };
  return payload.snapshot;
}

export function classifyCanonicalBuilderOutput(payload: {
  rawOutput: string;
  currentPriority?: string;
  latestDecision?: string;
}): OrchestrationClassification {
  const stdout = runCanonicalCommand(["api", "policy", "orchestration-classify", "--payload-json", JSON.stringify(payload)]);
  return JSON.parse(stdout) as OrchestrationClassification;
}

export function detectCanonicalCapabilityGaps(payload: {
  message: string;
  recentMessages: string[];
  taskNotes: string[];
  escalationTexts: string[];
  approvalCounts: Record<string, number>;
}): ImprovementDraft[] {
  const stdout = runCanonicalCommand(["api", "policy", "improvements", "detect", "--payload-json", JSON.stringify(payload)]);
  const parsed = JSON.parse(stdout) as { drafts: ImprovementDraft[] };
  return parsed.drafts;
}

export function getCanonicalTopImprovementFocus(): ImprovementRecord | null {
  const stdout = runCanonicalCommand(["api", "policy", "improvements", "focus"]);
  const parsed = JSON.parse(stdout) as { record: ImprovementRecord | null };
  return parsed.record;
}

export function buildCanonicalProjectDraft(payload: {
  goal: string;
  source: "goal" | "active_project" | "manual";
}): ProjectDraft {
  const stdout = runCanonicalCommand(["api", "policy", "project", "draft", "--payload-json", JSON.stringify(payload)]);
  return JSON.parse(stdout) as ProjectDraft;
}

export function getCanonicalProjectFocus(): ProjectFocusSnapshot | null {
  const stdout = runCanonicalCommand(["api", "policy", "project", "focus"]);
  const parsed = JSON.parse(stdout) as { focus: ProjectFocusSnapshot | null };
  return parsed.focus;
}

export type { ImprovementDraft, OrchestrationClassification, ProjectDraft };

