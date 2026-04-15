import { getConfig } from "@/src/core/config";
import { listCanonicalCoordinationRecords, putCanonicalCoordinationRecord } from "@/src/core/ari-spine/coordination-bridge";
import { listTasks } from "@/src/core/memory/repository";
import type { ExecutionOverview, ExecutionTrackedItem, ImprovementRecord } from "@/src/core/memory/types";
import { listImprovementLifecycle } from "@/src/core/agent/self-improvement";
import { listRecentDispatchRecords } from "@/src/core/orchestration/dispatch-records";

type OutcomeRow = {
  item_key: string;
  item_type: "task" | "improvement" | "dispatch" | "coding_action";
  item_id: string;
  title: string;
  state: "pending" | "moving" | "blocked" | "completed" | "failed";
  stage: string;
  state_since: string;
  last_progress_at: string;
  completed_at: string | null;
  blocked_reason: string | null;
  failure_reason: string | null;
  verification_signal: string | null;
  next_action: string;
  evidence_mode: "explicit" | "inferred";
  metadata_json: string;
  updated_at: string;
};

function now(): string {
  return new Date().toISOString();
}

function ageMinutes(value: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
}

function upsertOutcome(item: ExecutionTrackedItem): void {
  const timestamp = now();
  putCanonicalCoordinationRecord<OutcomeRow>("execution_outcome", {
    item_key: `${item.kind}:${item.id}`,
    item_type: item.kind,
    item_id: item.id,
    title: item.title,
    state: item.state,
    stage: item.stage,
    state_since: item.stateSince,
    last_progress_at: item.stateSince,
    completed_at: item.state === "completed" ? item.stateSince : null,
    blocked_reason: item.blockedReason || null,
    failure_reason: item.failureReason || null,
    verification_signal: item.verificationSignal || null,
    next_action: item.nextAction,
    evidence_mode: item.evidence,
    metadata_json: "{}",
    updated_at: timestamp
  });
}

function deriveTaskOutcomes(): ExecutionTrackedItem[] {
  const stallMinutes = getConfig().executionStallMinutes;
  return listTasks(12).map((task) => {
    const age = ageMinutes(task.updatedAt);
    if (task.status === "done") {
      return {
        id: task.id,
        kind: "task",
        title: task.title,
        state: "completed",
        stage: "done",
        stateSince: task.updatedAt,
        ageMinutes: age,
        nextAction: "No action required.",
        evidence: "explicit"
      } satisfies ExecutionTrackedItem;
    }

    if (age >= stallMinutes) {
      return {
        id: task.id,
        kind: "task",
        title: task.title,
        state: "blocked",
        stage: "stalled",
        stateSince: task.updatedAt,
        ageMinutes: age,
        blockedReason: "The task has not progressed within the allowed execution window.",
        nextAction: `Review or advance "${task.title}" now, or explicitly deprioritize it.`,
        evidence: "inferred"
      } satisfies ExecutionTrackedItem;
    }

    return {
      id: task.id,
      kind: "task",
      title: task.title,
      state: "moving",
      stage: "in_progress",
      stateSince: task.updatedAt,
      ageMinutes: age,
      nextAction: `Keep moving "${task.title}".`,
      evidence: "explicit"
    } satisfies ExecutionTrackedItem;
  });
}

function deriveImprovementOutcome(item: ImprovementRecord): ExecutionTrackedItem {
  const stallMinutes = getConfig().executionStallMinutes;
  const stateSince =
    item.verifiedAt ||
    item.completedAt ||
    item.dispatchedAt ||
    item.queuedAt ||
    item.approvedAt ||
    item.lastObservedAt;
  const age = ageMinutes(stateSince);

  if (item.status === "verified") {
    return {
      id: item.id,
      kind: "improvement",
      title: item.missingCapability,
      state: "completed",
      stage: "verified",
      stateSince,
      ageMinutes: age,
      verificationSignal: item.verificationEvidence || "explicit",
      nextAction: "No action required.",
      evidence: item.verificationEvidence || "explicit"
    };
  }

  if (item.status === "completed") {
    if (age >= stallMinutes) {
      return {
        id: item.id,
        kind: "improvement",
        title: item.missingCapability,
        state: "blocked",
        stage: "awaiting_verification",
        stateSince,
        ageMinutes: age,
        blockedReason: "Execution completed but verification evidence is still missing.",
        verificationSignal: item.completionEvidence,
        nextAction: "Verify the completed improvement before treating it as done.",
        evidence: item.completionEvidence || "inferred"
      };
    }

    return {
      id: item.id,
      kind: "improvement",
      title: item.missingCapability,
      state: "moving",
      stage: "awaiting_verification",
      stateSince,
      ageMinutes: age,
      verificationSignal: item.completionEvidence,
      nextAction: "Collect verification evidence now.",
      evidence: item.completionEvidence || "inferred"
    };
  }

  if (item.status === "dispatched") {
    if (!item.consumedAt && age >= stallMinutes) {
      return {
        id: item.id,
        kind: "improvement",
        title: item.missingCapability,
        state: "blocked",
        stage: "dispatched_not_consumed",
        stateSince,
        ageMinutes: age,
        blockedReason: "The builder instruction was dispatched but has not been picked up.",
        nextAction: "Check the builder consumer or re-dispatch through the builder channel.",
        evidence: item.dispatchEvidence || "inferred"
      };
    }

    return {
      id: item.id,
      kind: "improvement",
      title: item.missingCapability,
      state: "moving",
      stage: item.consumedAt ? "executing" : "dispatched",
      stateSince: item.consumedAt || stateSince,
      ageMinutes: ageMinutes(item.consumedAt || stateSince),
      nextAction: item.consumedAt ? "Wait for builder execution evidence." : "Wait for builder pickup or check the consumer.",
      evidence: item.dispatchEvidence || "inferred"
    };
  }

  if ((item.status === "approved" || item.status === "queued" || item.status === "proposed") && age >= stallMinutes) {
    return {
      id: item.id,
      kind: "improvement",
      title: item.missingCapability,
      state: "blocked",
      stage: item.status,
      stateSince,
      ageMinutes: age,
      blockedReason: "The improvement has not advanced beyond planning.",
      nextAction: item.nextBestAction,
      evidence: "explicit"
    };
  }

  return {
    id: item.id,
    kind: "improvement",
    title: item.missingCapability,
    state: "pending",
    stage: item.status,
    stateSince,
    ageMinutes: age,
    nextAction: item.nextBestAction,
    evidence: "explicit"
  };
}

function deriveImprovementOutcomes(): ExecutionTrackedItem[] {
  return listImprovementLifecycle(8).map(deriveImprovementOutcome);
}

function deriveDispatchOutcomes(): ExecutionTrackedItem[] {
  const stallMinutes = getConfig().executionStallMinutes;
  return listRecentDispatchRecords(6).map((record) => {
    if (record.verificationOrchestrationId) {
      return {
        id: record.id,
        kind: "dispatch",
        title: record.summary || "Builder dispatch",
        state: "completed",
        stage: "verified",
        stateSince: record.updatedAt,
        ageMinutes: ageMinutes(record.updatedAt),
        verificationSignal: "explicit",
        nextAction: "No action required.",
        evidence: "explicit"
      };
    }

    if (record.completionOrchestrationId) {
      return {
        id: record.id,
        kind: "dispatch",
        title: record.summary || "Builder dispatch",
        state: "moving",
        stage: "awaiting_verification",
        stateSince: record.updatedAt,
        ageMinutes: ageMinutes(record.updatedAt),
        nextAction: "Await or request explicit verification evidence.",
        evidence: "explicit"
      };
    }

    if (!record.consumedAt && ageMinutes(record.dispatchedAt) >= stallMinutes) {
      return {
        id: record.id,
        kind: "dispatch",
        title: record.summary || "Builder dispatch",
        state: "blocked",
        stage: "awaiting_consumption",
        stateSince: record.dispatchedAt,
        ageMinutes: ageMinutes(record.dispatchedAt),
        blockedReason: "The builder dispatch has not been consumed.",
        nextAction: "Check the builder consumer or re-dispatch if needed.",
        evidence: "explicit"
      };
    }

    if (record.consumedAt && ageMinutes(record.consumedAt) >= stallMinutes) {
      return {
        id: record.id,
        kind: "dispatch",
        title: record.summary || "Builder dispatch",
        state: "blocked",
        stage: "consumed_awaiting_result",
        stateSince: record.consumedAt,
        ageMinutes: ageMinutes(record.consumedAt),
        blockedReason: "The builder picked up the instruction but no result has been recorded.",
        nextAction: "Wait for builder output or inspect the builder run.",
        evidence: "explicit"
      };
    }

    return {
      id: record.id,
      kind: "dispatch",
      title: record.summary || "Builder dispatch",
      state: "moving",
      stage: record.consumedAt ? "executing" : "dispatched",
      stateSince: record.consumedAt || record.dispatchedAt,
      ageMinutes: ageMinutes(record.consumedAt || record.dispatchedAt),
      nextAction: record.consumedAt ? "Await builder result." : "Await builder pickup.",
      evidence: "explicit"
    };
  });
}

export function refreshExecutionOutcomes(): ExecutionOverview {
  const outcomes = [...deriveTaskOutcomes(), ...deriveImprovementOutcomes(), ...deriveDispatchOutcomes()];
  for (const item of outcomes) {
    upsertOutcome(item);
  }

  return {
    moving: outcomes.filter((item) => item.state === "moving").slice(0, 3),
    blocked: outcomes.filter((item) => item.state === "blocked").slice(0, 3),
    completed: outcomes.filter((item) => item.state === "completed").slice(0, 3)
  };
}

export function getExecutionOverview(): ExecutionOverview {
  const rows = listCanonicalCoordinationRecords<OutcomeRow>("execution_outcome", 24);

  const items: ExecutionTrackedItem[] = rows.map((row) => ({
    id: row.item_id,
    kind: row.item_type,
    title: row.title,
    state: row.state,
    stage: row.stage,
    stateSince: row.state_since,
    ageMinutes: ageMinutes(row.state_since),
    blockedReason: row.blocked_reason || undefined,
    failureReason: row.failure_reason || undefined,
    verificationSignal: row.verification_signal || undefined,
    nextAction: row.next_action,
    evidence: row.evidence_mode
  }));

  return {
    moving: items.filter((item) => item.state === "moving").slice(0, 3),
    blocked: items.filter((item) => item.state === "blocked").slice(0, 3),
    completed: items.filter((item) => item.state === "completed").slice(0, 3)
  };
}
