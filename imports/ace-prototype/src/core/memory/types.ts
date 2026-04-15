export type MemoryType =
  | "note"
  | "fact"
  | "preference"
  | "identity"
  | "goal"
  | "active_project"
  | "priority"
  | "routine"
  | "operating_principle"
  | "approval_decision"
  | "episodic_history"
  | "conversation_history"
  | "working_state";

export type MemoryRecord = {
  id: string;
  type: MemoryType;
  title: string;
  content: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
};

export type MessageRecord = {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

export type TaskRecord = {
  id: string;
  title: string;
  status: "open" | "done";
  notes: string;
  createdAt: string;
  updatedAt: string;
};

export type ProjectStatus = "active" | "blocked" | "completed";
export type ProjectMilestoneStatus = "pending" | "active" | "completed" | "blocked";
export type ProjectStepStatus = "pending" | "ready" | "blocked" | "in_progress" | "completed";

export type ProjectRecord = {
  id: string;
  title: string;
  goal: string;
  completionCriteria: string;
  status: ProjectStatus;
  source: "goal" | "active_project" | "manual";
  createdAt: string;
  updatedAt: string;
};

export type ProjectMilestoneRecord = {
  id: string;
  projectId: string;
  title: string;
  status: ProjectMilestoneStatus;
  completionCriteria: string;
  sequence: number;
  createdAt: string;
  updatedAt: string;
};

export type ProjectStepRecord = {
  id: string;
  projectId: string;
  milestoneId: string;
  title: string;
  status: ProjectStepStatus;
  completionCriteria: string;
  dependsOnStepIds: string[];
  blockedBy: string[];
  sequence: number;
  linkedTaskId?: string;
  linkedImprovementId?: string;
  createdAt: string;
  updatedAt: string;
};

export type ProjectFocusSnapshot = {
  project: ProjectRecord;
  currentMilestone: ProjectMilestoneRecord | null;
  nextStep: ProjectStepRecord | null;
  majorBlocker: string | null;
  completionCriteria: string;
  progressSummary: string;
};

export type ExecutionState = "pending" | "moving" | "blocked" | "completed" | "failed";

export type ExecutionTrackedItem = {
  id: string;
  kind: "task" | "improvement" | "dispatch";
  title: string;
  state: ExecutionState;
  stage: string;
  stateSince: string;
  ageMinutes: number;
  blockedReason?: string;
  failureReason?: string;
  verificationSignal?: string;
  nextAction: string;
  evidence: "explicit" | "inferred";
};

export type ExecutionOverview = {
  moving: ExecutionTrackedItem[];
  blocked: ExecutionTrackedItem[];
  completed: ExecutionTrackedItem[];
};

export type DecisionRecord = {
  id: string;
  title: string;
  body: string;
  source: "approval" | "orchestration";
  createdAt: string;
};

export type HistoryRecord = {
  id: string;
  type: "message" | "event" | "approval" | "orchestration";
  title: string;
  body: string;
  createdAt: string;
};

export type WorkingStateSignal = {
  id: string;
  title: string;
  body: string;
  kind: "priority" | "decision" | "pattern" | "runtime";
  createdAt: string;
};

export type FocusKind = "approval" | "task" | "improvement" | "orchestration" | "decision" | "project";

export type AwarenessFocusItem = {
  id: string;
  kind: FocusKind;
  title: string;
  reason: string;
  nextAction: string;
  score: number;
  blocking: boolean;
  sourceId?: string;
};

export type AwarenessSnapshot = {
  id: string;
  mode: "blocked" | "active" | "steady";
  summary: string;
  currentFocus: AwarenessFocusItem[];
  tracking: string[];
  recentIntent: string[];
  signature: string;
  updatedAt: string;
};

export type ImprovementStatus = "proposed" | "approved" | "queued" | "dispatched" | "completed" | "verified";

export type ImprovementPriority = "highest" | "high" | "medium";

export type ExecutionEvidenceMode = "explicit" | "inferred";

export type ImprovementReflection = {
  repeatedLimitations: number;
  repeatedUserFriction: number;
  repeatedManualSteps: number;
  repeatedEscalationCauses: number;
  total: number;
};

export type ImprovementRecord = {
  id: string;
  capability: string;
  missingCapability: string;
  whyItMatters: string;
  whatItUnlocks: string;
  smallestSlice: string;
  nextBestAction: string;
  approvalRequired: boolean;
  relativePriority: ImprovementPriority;
  leverage: number;
  urgency: number;
  dependencyValue: number;
  autonomyImpact: number;
  implementationEffort: number;
  priorityScore: number;
  status: ImprovementStatus;
  approvalId?: string;
  taskId?: string;
  dedupeKey: string;
  instructionOrchestrationId?: string;
  dispatchRecordId?: string;
  dispatchOrchestrationId?: string;
  dispatchMode?: "manual" | "assisted" | "auto";
  dispatchEvidence?: ExecutionEvidenceMode;
  consumedAt?: string;
  consumer?: string;
  completionOrchestrationId?: string;
  completionEvidence?: ExecutionEvidenceMode;
  verificationOrchestrationId?: string;
  verificationEvidence?: ExecutionEvidenceMode;
  reflection: ImprovementReflection;
  firstObservedAt: string;
  lastObservedAt: string;
  approvedAt?: string;
  queuedAt?: string;
  dispatchedAt?: string;
  completedAt?: string;
  verifiedAt?: string;
};

export type ActiveStateSnapshot = {
  knownAboutAlec: MemoryRecord[];
  currentPriorities: MemoryRecord[];
  activeProjects: MemoryRecord[];
  currentTasks: TaskRecord[];
  pendingApprovals: Array<{
    id: string;
    title: string;
    body: string;
    createdAt: string;
  }>;
  recentDecisions: DecisionRecord[];
  recentHistory: HistoryRecord[];
  workingStateSignals: WorkingStateSignal[];
  topImprovement: ImprovementRecord | null;
  improvementLifecycle: ImprovementRecord[];
  awareness: AwarenessSnapshot | null;
  execution: ExecutionOverview;
  projectFocus: ProjectFocusSnapshot | null;
  operatorChannels: OperatorChannelSnapshot;
};

export type MemoryContext = {
  relevantMemories: MemoryRecord[];
  knownAboutAlec: MemoryRecord[];
  currentPriorities: MemoryRecord[];
  activeProjects: MemoryRecord[];
  operatingPrinciples: MemoryRecord[];
  recentDecisions: DecisionRecord[];
  recentHistory: HistoryRecord[];
  workingStateSignals: WorkingStateSignal[];
  topImprovement: ImprovementRecord | null;
  improvementLifecycle: ImprovementRecord[];
  awareness: AwarenessSnapshot | null;
  execution: ExecutionOverview;
  projectFocus: ProjectFocusSnapshot | null;
  operatorChannels: OperatorChannelSnapshot;
  summaryLines: string[];
};

export type OperatorChannelId =
  | "builder_dispatch_consumer"
  | "shortcut_entry"
  | "notification_delivery"
  | "interface_control"
  | "mobile_delivery";

export type OperatorChannelStatus = "available" | "partial" | "blocked";

export type OperatorChannelRecord = {
  id: OperatorChannelId;
  label: string;
  status: OperatorChannelStatus;
  summary: string;
  availableActions: string[];
  approvalRequired: boolean;
  blocker?: string;
  nextUnlock?: string;
};

export type OperatorChannelSnapshot = {
  channels: OperatorChannelRecord[];
  majorBlocker: OperatorChannelRecord | null;
  executionOpportunities: string[];
};
