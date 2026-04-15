import { buildAwarenessSnapshot } from "@/src/core/agent/awareness";
import { getExecutionOverview, refreshExecutionOutcomes } from "@/src/core/agent/execution";
import { getCanonicalCodingExecutionSnapshot } from "@/src/core/ari-spine/execution-bridge";
import { getTopImprovementFocus, listImprovementLifecycle } from "@/src/core/agent/self-improvement";
import { ensureProjectPlanFromMemory, syncProjectExecutionState } from "@/src/core/planning/project-planning";
import { buildOperatorChannelSnapshot, summarizeOperatorChannelState } from "@/src/core/operator/channels";
import { getOrchestrationSnapshot } from "@/src/core/orchestration/repository";
import {
  listMemoriesByTypes,
  listRecentDecisions,
  listRecentHistory,
  listTasks,
  rememberMemory,
  retrieveMemories
} from "@/src/core/memory/repository";
import type { ActiveStateSnapshot, MemoryContext, MemoryRecord, MemoryType, WorkingStateSignal } from "@/src/core/memory/types";
import { getDatabase } from "@/src/core/db/database";

function createMemoryTitle(content: string, fallback: string): string {
  const cleaned = content.trim().replace(/[.?!]+$/, "");
  if (!cleaned) {
    return fallback;
  }
  return cleaned.length > 64 ? `${cleaned.slice(0, 61)}...` : cleaned;
}

function buildMemorySummary(memory: MemoryRecord): string {
  return `${memory.type}: ${memory.title} => ${memory.content}`;
}

function isStaticBuildPhase(): boolean {
  const phase = process.env.NEXT_PHASE || "";
  return phase.includes("phase-production-build");
}

function seedMemorySafely(type: MemoryType, title: string, content: string, tags: string[]): void {
  try {
    rememberMemory(type, title, content, tags);
  } catch {
    // Build-time and read-only contexts should not fail because the canonical memory spine
    // cannot be mutated in that environment. Runtime writes still converge inward when allowed.
  }
}

function collectSignals(state: ActiveStateSnapshot): WorkingStateSignal[] {
  const signals: WorkingStateSignal[] = [];
  const timestamp = new Date().toISOString();

  if (state.currentPriorities[0]) {
    signals.push({
      id: `priority-${state.currentPriorities[0].id}`,
      title: "Current priority in memory",
      body: state.currentPriorities[0].content,
      kind: "priority",
      createdAt: state.currentPriorities[0].updatedAt
    });
  }

  if (state.recentDecisions[0]) {
    signals.push({
      id: `decision-${state.recentDecisions[0].id}`,
      title: "Recent operator decision",
      body: state.recentDecisions[0].body,
      kind: "decision",
      createdAt: state.recentDecisions[0].createdAt
    });
  }

  if (state.currentTasks.length) {
    signals.push({
      id: "pattern-open-work",
      title: "Open work is active",
      body: `${state.currentTasks.length} task(s) remain open. Lead item: ${state.currentTasks[0].title}.`,
      kind: "pattern",
      createdAt: timestamp
    });
  }

  if (state.pendingApprovals.length) {
    signals.push({
      id: "runtime-pending-approvals",
      title: "Approvals are waiting",
      body: `${state.pendingApprovals.length} approval request(s) are waiting for Alec.`,
      kind: "runtime",
      createdAt: timestamp
    });
  }

  if (state.topImprovement && state.topImprovement.status !== "verified") {
    signals.push({
      id: `improvement-${state.topImprovement.id}`,
      title: "Self-improvement focus is active",
      body: `${state.topImprovement.missingCapability} is ${state.topImprovement.status} at ${state.topImprovement.relativePriority} priority.`,
      kind: "runtime",
      createdAt: state.topImprovement.lastObservedAt
    });
  }

  if (state.awareness?.currentFocus[0]) {
    signals.push({
      id: `focus-${state.awareness.currentFocus[0].id}`,
      title: "Current focus",
      body: `${state.awareness.currentFocus[0].title}. ${state.awareness.currentFocus[0].nextAction}`,
      kind: state.awareness.currentFocus[0].blocking ? "runtime" : "priority",
      createdAt: state.awareness.updatedAt
    });
  }

  if (state.projectFocus?.nextStep) {
    signals.push({
      id: `project-${state.projectFocus.project.id}`,
      title: "Project execution path is active",
      body: `${state.projectFocus.project.title}. Next valid step: ${state.projectFocus.nextStep.title}.`,
      kind: "priority",
      createdAt: state.projectFocus.project.updatedAt
    });
  }

  const orchestration = getOrchestrationSnapshot();
  if (orchestration.control.paused) {
    signals.push({
      id: "runtime-orchestration-paused",
      title: "Builder loop is paused",
      body: orchestration.control.pauseReason || "ARI is waiting for Alec before continuing orchestration.",
      kind: "runtime",
      createdAt: timestamp
    });
  }

  if (state.operatorChannels.majorBlocker) {
    signals.push({
      id: `channel-${state.operatorChannels.majorBlocker.id}`,
      title: "Major autonomy blocker",
      body: `${state.operatorChannels.majorBlocker.label}: ${state.operatorChannels.majorBlocker.summary}`,
      kind: "runtime",
      createdAt: timestamp
    });
  }

  if (state.codingExecution.currentAction) {
    signals.push({
      id: `coding-${state.codingExecution.currentAction.id}`,
      title: "Coding action is active",
      body: `${state.codingExecution.currentAction.title} is ${state.codingExecution.currentAction.status}. ${state.codingExecution.currentAction.resultSummary}`,
      kind: state.codingExecution.currentAction.status === "failed" ? "runtime" : "priority",
      createdAt: state.codingExecution.currentAction.updatedAt
    });
  }

  return signals.slice(0, 5);
}

export function ensureCoreMemorySeed(): void {
  if (isStaticBuildPhase()) {
    return;
  }
  seedMemorySafely("identity", "Operator", "This hub is private and single-user first for Alec.", ["alec", "operator"]);
  seedMemorySafely("operating_principle", "ARI vs ACE", "ARI is the brain. ACE is the manifestation and interface layer.", [
    "ari",
    "ace",
    "canon"
  ]);
}

export function captureStructuredMemoriesFromMessage(message: string): MemoryRecord[] {
  const trimmed = message.trim();
  if (!trimmed) {
    return [];
  }

  const captures: Array<{ type: MemoryType; title: string; content: string; tags?: string[] }> = [];
  const lower = trimmed.toLowerCase();

  let match = trimmed.match(/^my priority is\s+(.+)$/i) || trimmed.match(/^current priority:\s*(.+)$/i);
  if (match) {
    captures.push({
      type: "priority",
      title: createMemoryTitle(match[1], "Current priority"),
      content: match[1].trim(),
      tags: ["priority", "current"]
    });
  }

  match = trimmed.match(/^(?:i am|i'm)\s+working on\s+(.+)$/i) || trimmed.match(/^active project:\s*(.+)$/i);
  if (match) {
    captures.push({
      type: "active_project",
      title: createMemoryTitle(match[1], "Active project"),
      content: match[1].trim(),
      tags: ["project", "active"]
    });
  }

  match = trimmed.match(/^my goal is\s+(.+)$/i) || trimmed.match(/^goal:\s*(.+)$/i);
  if (match) {
    captures.push({
      type: "goal",
      title: createMemoryTitle(match[1], "Goal"),
      content: match[1].trim(),
      tags: ["goal"]
    });
  }

  match = trimmed.match(/^my routine is\s+(.+)$/i) || trimmed.match(/^routine:\s*(.+)$/i);
  if (match) {
    captures.push({
      type: "routine",
      title: createMemoryTitle(match[1], "Routine"),
      content: match[1].trim(),
      tags: ["routine"]
    });
  }

  match = trimmed.match(/^my operating principle is\s+(.+)$/i) || trimmed.match(/^operating principle:\s*(.+)$/i);
  if (match) {
    captures.push({
      type: "operating_principle",
      title: createMemoryTitle(match[1], "Operating principle"),
      content: match[1].trim(),
      tags: ["principle"]
    });
  }

  if (/\b(alec)\b/i.test(trimmed) && /\b(i am|i'm|my name is)\b/i.test(lower)) {
    captures.push({
      type: "identity",
      title: "Alec identity",
      content: trimmed,
      tags: ["alec", "identity"]
    });
  }

  return captures.map((capture) => rememberMemory(capture.type, capture.title, capture.content, capture.tags || []));
}

export function rememberOperatorDecision(title: string, content: string, tags: string[] = []): MemoryRecord {
  return rememberMemory("approval_decision", title, content, tags);
}

export function getActiveStateSnapshot(): ActiveStateSnapshot {
  ensureCoreMemorySeed();
  ensureProjectPlanFromMemory();
  const database = getDatabase();
  const orchestration = getOrchestrationSnapshot();
  const pendingApprovals = database
    .prepare(
      `SELECT id, title, body, created_at
       FROM approvals
       WHERE status = 'pending'
       ORDER BY created_at DESC
       LIMIT 6`
    )
    .all() as Array<{
    id: string;
    title: string;
    body: string;
    created_at: string;
  }>;

  const state: ActiveStateSnapshot = {
    knownAboutAlec: listMemoriesByTypes(["identity", "preference", "goal", "routine", "operating_principle"], 8),
    currentPriorities: listMemoriesByTypes(["priority"], 4),
    activeProjects: listMemoriesByTypes(["active_project"], 4),
    currentTasks: listTasks(8).filter((task) => task.status === "open"),
    pendingApprovals: pendingApprovals.map((row) => ({
      id: row.id,
      title: row.title,
      body: row.body,
      createdAt: row.created_at
    })),
    recentDecisions: listRecentDecisions(6),
    recentHistory: listRecentHistory(10),
    workingStateSignals: [],
    topImprovement: getTopImprovementFocus(),
    improvementLifecycle: listImprovementLifecycle(4),
    awareness: null,
    execution: { moving: [], blocked: [], completed: [] },
    codingExecution: getCanonicalCodingExecutionSnapshot(),
    projectFocus: syncProjectExecutionState(),
    operatorChannels: {
      channels: [],
      majorBlocker: null,
      executionOpportunities: []
    }
  };

  refreshExecutionOutcomes();
  state.execution = getExecutionOverview();
  state.operatorChannels = buildOperatorChannelSnapshot({
    orchestration,
    pendingApprovalsCount: state.pendingApprovals.length,
    topImprovementCapability: state.topImprovement?.missingCapability
  });
  state.awareness = buildAwarenessSnapshot(state);
  state.workingStateSignals = collectSignals(state);
  return state;
}

export function retrieveMemoryContext(query: string): MemoryContext {
  ensureCoreMemorySeed();
  const state = getActiveStateSnapshot();
  const relevantMemories = retrieveMemories(query, 6);
  const operatingPrinciples = listMemoriesByTypes(["operating_principle"], 4);

  const summaryLines = [
    ...state.currentPriorities.slice(0, 2).map((memory) => `Current priority: ${memory.content}`),
    ...state.activeProjects.slice(0, 2).map((memory) => `Active project: ${memory.content}`),
    ...(state.projectFocus
      ? [
          `Project focus: ${state.projectFocus.project.title}`,
          state.projectFocus.currentMilestone ? `Current milestone: ${state.projectFocus.currentMilestone.title}` : "",
          state.projectFocus.nextStep ? `Next valid step: ${state.projectFocus.nextStep.title}` : "",
          state.projectFocus.majorBlocker ? `Project blocker: ${state.projectFocus.majorBlocker}` : ""
        ].filter(Boolean)
      : []),
    ...state.knownAboutAlec.slice(0, 3).map((memory) => `Known about Alec: ${memory.content}`),
    ...state.recentDecisions.slice(0, 2).map((decision) => `Recent decision: ${decision.body}`),
    ...state.recentHistory.slice(0, 2).map((item) => `Recent history: ${item.title} => ${item.body}`),
    ...state.execution.blocked.slice(0, 2).map((item) => `Blocked: ${item.title} => ${item.blockedReason}`),
    ...state.execution.moving.slice(0, 2).map((item) => `Moving: ${item.title} => ${item.nextAction}`),
    ...(state.codingExecution.currentAction
      ? [
          `Coding action: ${state.codingExecution.currentAction.title} (${state.codingExecution.currentAction.status}).`,
          `Coding step: ${state.codingExecution.currentAction.currentStep}`,
          `Coding result: ${state.codingExecution.currentAction.resultSummary}`,
          state.codingExecution.lastCommandRun
            ? `Last command: ${state.codingExecution.lastCommandRun.command} => ${
                state.codingExecution.lastCommandRun.success ? "passed" : "failed"
              }`
            : ""
        ].filter(Boolean)
      : []),
    ...summarizeOperatorChannelState(state.operatorChannels),
    ...(state.awareness
      ? [
          `Current focus: ${state.awareness.summary}`,
          ...state.awareness.currentFocus.slice(0, 2).map((item) => `Focus item: ${item.title} => ${item.nextAction}`),
          ...state.awareness.tracking.slice(0, 2).map((item) => `Tracking: ${item}`)
        ]
      : []),
    ...state.workingStateSignals.slice(0, 2).map((signal) => `Working state: ${signal.body}`),
    ...(state.topImprovement
      ? [
          `Self-improvement focus: ${state.topImprovement.missingCapability} (${state.topImprovement.relativePriority}, ${state.topImprovement.status}).`,
          `Unlocks: ${state.topImprovement.whatItUnlocks}`
        ]
      : []),
    ...relevantMemories.slice(0, 4).map(buildMemorySummary)
  ].slice(0, 12);

  return {
    relevantMemories,
    knownAboutAlec: state.knownAboutAlec,
    currentPriorities: state.currentPriorities,
    activeProjects: state.activeProjects,
    operatingPrinciples,
    recentDecisions: state.recentDecisions,
    recentHistory: state.recentHistory,
    workingStateSignals: state.workingStateSignals,
    topImprovement: state.topImprovement,
    improvementLifecycle: state.improvementLifecycle,
    awareness: state.awareness,
    execution: getExecutionOverview(),
    codingExecution: state.codingExecution,
    projectFocus: state.projectFocus,
    operatorChannels: state.operatorChannels,
    summaryLines
  };
}
