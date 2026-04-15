import { buildCanonicalProjectDraft, getCanonicalProjectFocus } from "@/src/core/ari-spine/policy-bridge";
import { getImprovementById } from "@/src/core/agent/self-improvement";
import { listCanonicalCoordinationRecords, putCanonicalCoordinationRecord } from "@/src/core/ari-spine/coordination-bridge";
import { createTask, getTaskById, listMemoriesByTypes, rememberMemory } from "@/src/core/memory/repository";
import type {
  ProjectFocusSnapshot,
  ProjectMilestoneRecord,
  ProjectMilestoneStatus,
  ProjectRecord,
  ProjectStatus,
  ProjectStepRecord,
  ProjectStepStatus
} from "@/src/core/memory/types";

type ProjectRow = {
  id: string;
  title: string;
  goal: string;
  completion_criteria: string;
  status: ProjectStatus;
  source: "goal" | "active_project" | "manual";
  created_at: string;
  updated_at: string;
};

type MilestoneRow = {
  id: string;
  project_id: string;
  title: string;
  status: ProjectMilestoneStatus;
  completion_criteria: string;
  sequence: number;
  created_at: string;
  updated_at: string;
};

type StepRow = {
  id: string;
  project_id: string;
  milestone_id: string;
  title: string;
  status: ProjectStepStatus;
  completion_criteria: string;
  depends_on_step_ids_json: string;
  blocked_by_json: string;
  sequence: number;
  linked_task_id: string | null;
  linked_improvement_id: string | null;
  created_at: string;
  updated_at: string;
};

function now(): string {
  return new Date().toISOString();
}

function compactTitle(value: string, max = 68): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return "Project";
  }
  return normalized.length <= max ? normalized : `${normalized.slice(0, max - 3)}...`;
}

function parseJsonArray(raw: string | null): string[] {
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as string[];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function mapProjectRow(row: ProjectRow): ProjectRecord {
  return {
    id: row.id,
    title: row.title,
    goal: row.goal,
    completionCriteria: row.completion_criteria,
    status: row.status,
    source: row.source,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function mapMilestoneRow(row: MilestoneRow): ProjectMilestoneRecord {
  return {
    id: row.id,
    projectId: row.project_id,
    title: row.title,
    status: row.status,
    completionCriteria: row.completion_criteria,
    sequence: row.sequence,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function mapStepRow(row: StepRow): ProjectStepRecord {
  return {
    id: row.id,
    projectId: row.project_id,
    milestoneId: row.milestone_id,
    title: row.title,
    status: row.status,
    completionCriteria: row.completion_criteria,
    dependsOnStepIds: parseJsonArray(row.depends_on_step_ids_json),
    blockedBy: parseJsonArray(row.blocked_by_json),
    sequence: row.sequence,
    linkedTaskId: row.linked_task_id || undefined,
    linkedImprovementId: row.linked_improvement_id || undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function recordToProjectRow(record: ProjectRecord): ProjectRow {
  return {
    id: record.id,
    title: record.title,
    goal: record.goal,
    completion_criteria: record.completionCriteria,
    status: record.status,
    source: record.source,
    created_at: record.createdAt,
    updated_at: record.updatedAt
  };
}

function recordToMilestoneRow(record: ProjectMilestoneRecord): MilestoneRow {
  return {
    id: record.id,
    project_id: record.projectId,
    title: record.title,
    status: record.status,
    completion_criteria: record.completionCriteria,
    sequence: record.sequence,
    created_at: record.createdAt,
    updated_at: record.updatedAt
  };
}

function recordToStepRow(record: ProjectStepRecord): StepRow {
  return {
    id: record.id,
    project_id: record.projectId,
    milestone_id: record.milestoneId,
    title: record.title,
    status: record.status,
    completion_criteria: record.completionCriteria,
    depends_on_step_ids_json: JSON.stringify(record.dependsOnStepIds),
    blocked_by_json: JSON.stringify(record.blockedBy),
    sequence: record.sequence,
    linked_task_id: record.linkedTaskId || null,
    linked_improvement_id: record.linkedImprovementId || null,
    created_at: record.createdAt,
    updated_at: record.updatedAt
  };
}

function listProjects(limit = 8): ProjectRecord[] {
  const rows = listCanonicalCoordinationRecords<ProjectRow>("project", limit);

  return rows.map(mapProjectRow);
}

function listMilestones(projectId: string): ProjectMilestoneRecord[] {
  const rows = listCanonicalCoordinationRecords<MilestoneRow>("project_milestone", 200).filter((row) => row.project_id === projectId);

  return rows.map(mapMilestoneRow);
}

function listSteps(projectId: string): ProjectStepRecord[] {
  const rows = listCanonicalCoordinationRecords<StepRow>("project_step", 500).filter((row) => row.project_id === projectId);

  return rows.map(mapStepRow);
}

function findExistingProjectByGoal(goal: string): ProjectRecord | null {
  const row = listCanonicalCoordinationRecords<ProjectRow>("project", 100).find((project) => project.goal === goal.trim());

  return row ? mapProjectRow(row) : null;
}

function updateProjectStatus(projectId: string, status: ProjectStatus): void {
  const current = listProjects(100).find((project) => project.id === projectId);
  if (!current) {
    return;
  }
  putCanonicalCoordinationRecord<ProjectRow>("project", recordToProjectRow({ ...current, status, updatedAt: now() }));
}

function updateMilestoneStatus(milestoneId: string, status: ProjectMilestoneStatus): void {
  const current = listCanonicalCoordinationRecords<MilestoneRow>("project_milestone", 500).find((milestone) => milestone.id === milestoneId);
  if (!current) {
    return;
  }
  putCanonicalCoordinationRecord<MilestoneRow>("project_milestone", { ...current, status, updated_at: now() });
}

function updateStepState(stepId: string, status: ProjectStepStatus, blockedBy: string[]): void {
  const current = listCanonicalCoordinationRecords<StepRow>("project_step", 1000).find((step) => step.id === stepId);
  if (!current) {
    return;
  }
  putCanonicalCoordinationRecord<StepRow>("project_step", {
    ...current,
    status,
    blocked_by_json: JSON.stringify(blockedBy),
    updated_at: now()
  });
}

export function createProjectPlan(goal: string, source: "goal" | "active_project" | "manual" = "manual"): ProjectFocusSnapshot {
  const existing = findExistingProjectByGoal(goal);
  if (existing) {
    return getCurrentProjectFocus() || {
      project: existing,
      currentMilestone: null,
      nextStep: null,
      majorBlocker: null,
      completionCriteria: existing.completionCriteria,
      progressSummary: `${existing.title} is already in ARI's planning spine.`
    };
  }

  const draft = buildCanonicalProjectDraft({ goal, source });
  const timestamp = now();
  const projectId = crypto.randomUUID();
  putCanonicalCoordinationRecord<ProjectRow>("project", {
    id: projectId,
    title: draft.title,
    goal: draft.goal,
    completion_criteria: draft.completionCriteria,
    status: "active",
    source: draft.source,
    created_at: timestamp,
    updated_at: timestamp
  });

  const flattenedStepIds: string[] = [];
  const milestoneIds: string[] = [];
  for (const milestone of draft.milestones) {
    milestoneIds.push(crypto.randomUUID());
    for (const _step of milestone.steps) {
      flattenedStepIds.push(crypto.randomUUID());
    }
  }

  let milestoneIndex = 0;
  let flatStepIndex = 0;
  for (const milestone of draft.milestones) {
    const milestoneId = milestoneIds[milestoneIndex];
    putCanonicalCoordinationRecord<MilestoneRow>("project_milestone", {
      id: milestoneId,
      project_id: projectId,
      title: milestone.title,
      status: milestoneIndex === 0 ? "active" : "pending",
      completion_criteria: milestone.completionCriteria,
      sequence: milestoneIndex,
      created_at: timestamp,
      updated_at: timestamp
    });

    for (const step of milestone.steps) {
      const stepId = flattenedStepIds[flatStepIndex];
      const dependsOnStepIds = step.dependsOnIndexes.map((index) => flattenedStepIds[index]).filter(Boolean);
      const task = createTask(step.title, step.completionCriteria);
      putCanonicalCoordinationRecord<StepRow>("project_step", {
        id: stepId,
        project_id: projectId,
        milestone_id: milestoneId,
        title: step.title,
        status: dependsOnStepIds.length ? "blocked" : "ready",
        completion_criteria: step.completionCriteria,
        depends_on_step_ids_json: JSON.stringify(dependsOnStepIds),
        blocked_by_json: JSON.stringify([]),
        sequence: flatStepIndex,
        linked_task_id: task.id,
        linked_improvement_id: step.linkedImprovementId || null,
        created_at: timestamp,
        updated_at: timestamp
      });
      flatStepIndex += 1;
    }

    milestoneIndex += 1;
  }

  rememberMemory("active_project", draft.title, draft.goal, ["project", "planned"]);
  return syncProjectExecutionState()!;
}

export function ensureProjectPlanFromMemory(): ProjectFocusSnapshot | null {
  if (listProjects(1)[0]) {
    return syncProjectExecutionState();
  }

  const candidate = listMemoriesByTypes(["active_project", "goal"], 2)[0];
  if (!candidate) {
    return null;
  }

  return createProjectPlan(candidate.content, candidate.type === "goal" ? "goal" : "active_project");
}

export function syncProjectExecutionState(): ProjectFocusSnapshot | null {
  return getCanonicalProjectFocus();
}

export function getCurrentProjectFocus(): ProjectFocusSnapshot | null {
  return getCanonicalProjectFocus();
}
