import { buildTaskSummary, createFocusBriefApproval, hasRecentEvent, listPendingApprovals, recordAriEvent } from "@/src/core/agent/activity";
import { storeAwarenessSnapshot } from "@/src/core/agent/awareness";
import { refreshExecutionOutcomes } from "@/src/core/agent/execution";
import { getTopImprovementFocus } from "@/src/core/agent/self-improvement";
import { listPendingBuilderOutputs } from "@/src/core/orchestration/repository";
import { ingestBuilderOutputsFromChannel, processPendingBuilderOutputs } from "@/src/core/orchestration/processor";
import { processBuilderDispatchConsumerOnce } from "@/src/core/operator/builder-consumer";
import { saveCanonicalNote } from "@/src/core/ari-spine/notes-bridge";
import { getActiveStateSnapshot } from "@/src/core/memory/spine";
import { listTasks } from "@/src/core/memory/repository";

type BackgroundState = {
  started: boolean;
  running: boolean;
  timer: NodeJS.Timeout | null;
};

declare global {
  var __ariBackgroundState: BackgroundState | undefined;
}

function getState(): BackgroundState {
  if (!globalThis.__ariBackgroundState) {
    globalThis.__ariBackgroundState = {
      started: false,
      running: false,
      timer: null
    };
  }

  return globalThis.__ariBackgroundState;
}

function getIntervalMs(): number {
  const raw = Number(process.env.ARI_BACKGROUND_INTERVAL_MS || 45000);
  return Number.isFinite(raw) && raw >= 5000 ? raw : 45000;
}

function markRuntimeOnline(): void {
  if (!hasRecentEvent("system:runtime-online", 24 * 60)) {
    recordAriEvent({
      type: "observation_generated",
      title: "ARI runtime is active",
      body: "ACE is attached as the hub interface. ARI is monitoring tasks, memory, and operator activity.",
      autonomyLevel: "report",
      dedupeKey: "system:runtime-online"
    });
  }
}

function emitAwarenessSignals(): boolean {
  const state = getActiveStateSnapshot();
  const awareness = state.awareness;
  if (!awareness) {
    return false;
  }

  const stored = storeAwarenessSnapshot(awareness);
  let producedWork = false;

  if (stored.changed && !hasRecentEvent(`awareness:${awareness.signature}`, 12 * 60)) {
    recordAriEvent({
      type: "observation_generated",
      title: "Current focus updated",
      body: awareness.summary,
      autonomyLevel: "report",
      dedupeKey: `awareness:${awareness.signature}`,
      metadata: {
        mode: awareness.mode,
        focus: awareness.currentFocus.map((item) => ({
          kind: item.kind,
          title: item.title,
          blocking: item.blocking
        }))
      }
    });
    producedWork = true;
  }

  const leadFocus = awareness.currentFocus[0];
  if (!leadFocus) {
    return producedWork;
  }

  if (
    leadFocus.kind === "orchestration" &&
    !hasRecentEvent(`focus:orchestration:${leadFocus.sourceId}`, 90)
  ) {
    recordAriEvent({
      type: "observation_generated",
      title: "Builder loop is waiting on Alec",
      body: `${leadFocus.reason} ${leadFocus.nextAction}`,
      autonomyLevel: "report",
      dedupeKey: `focus:orchestration:${leadFocus.sourceId}`,
      metadata: { sourceId: leadFocus.sourceId }
    });
    return true;
  }

  if (
    leadFocus.kind === "approval" &&
    !hasRecentEvent(`focus:approval:${leadFocus.sourceId}`, 90)
  ) {
    recordAriEvent({
      type: "suggestion_generated",
      title: "Resolve the pending approval",
      body: `${leadFocus.reason} ${leadFocus.nextAction}`,
      autonomyLevel: "propose",
      dedupeKey: `focus:approval:${leadFocus.sourceId}`,
      metadata: { sourceId: leadFocus.sourceId }
    });
    return true;
  }

  if (
    leadFocus.kind === "task" &&
    !hasRecentEvent(`focus:task:${leadFocus.sourceId}`, 90)
  ) {
    recordAriEvent({
      type: "suggestion_generated",
      title: "Advance the current focus task",
      body: `${leadFocus.reason} ${leadFocus.nextAction}`,
      autonomyLevel: "propose",
      dedupeKey: `focus:task:${leadFocus.sourceId}`,
      metadata: { sourceId: leadFocus.sourceId }
    });
    return true;
  }

  if (
    leadFocus.kind === "improvement" &&
    !hasRecentEvent(`focus:improvement:${leadFocus.sourceId}`, 120)
  ) {
    recordAriEvent({
      type: "suggestion_generated",
      title: "Advance the top self-improvement",
      body: `${leadFocus.reason} ${leadFocus.nextAction}`,
      autonomyLevel: "propose",
      dedupeKey: `focus:improvement:${leadFocus.sourceId}`,
      metadata: { sourceId: leadFocus.sourceId }
    });
    return true;
  }

  return producedWork;
}

function emitExecutionSignals(): boolean {
  const execution = refreshExecutionOutcomes();
  let producedWork = false;

  for (const item of execution.blocked.slice(0, 2)) {
    const key = `execution:block:${item.kind}:${item.id}:${item.stage}`;
    if (hasRecentEvent(key, 90)) {
      continue;
    }
    recordAriEvent({
      type: "observation_generated",
      title: `${item.kind[0].toUpperCase()}${item.kind.slice(1)} is blocked`,
      body: `${item.title}. ${item.blockedReason || "Execution is not moving."} Next step: ${item.nextAction}`,
      autonomyLevel: "report",
      dedupeKey: key,
      metadata: { kind: item.kind, itemId: item.id, stage: item.stage, ageMinutes: item.ageMinutes, evidence: item.evidence }
    });
    producedWork = true;
  }

  for (const item of execution.moving.slice(0, 1)) {
    const key = `execution:moving:${item.kind}:${item.id}:${item.stage}`;
    if (hasRecentEvent(key, 120)) {
      continue;
    }
    recordAriEvent({
      type: "suggestion_generated",
      title: `${item.title} is in motion`,
      body: `${item.kind} is ${item.stage.replace(/_/g, " ")}. Next step: ${item.nextAction}`,
      autonomyLevel: "propose",
      dedupeKey: key,
      metadata: { kind: item.kind, itemId: item.id, stage: item.stage, ageMinutes: item.ageMinutes }
    });
    producedWork = true;
  }

  return producedWork;
}

export function ensureBackgroundRuntime(): void {
  const state = getState();
  if (state.started) {
    return;
  }

  markRuntimeOnline();
  state.started = true;
  state.timer = setInterval(() => {
    void runBackgroundCycleOnce("interval");
  }, getIntervalMs());
  state.timer.unref();
  void runBackgroundCycleOnce("startup");
}

export function stopBackgroundRuntime(): void {
  const state = getState();
  if (state.timer) {
    clearInterval(state.timer);
  }

  state.started = false;
  state.running = false;
  state.timer = null;
}

export async function runBackgroundCycleOnce(reason: "startup" | "interval" | "manual" = "manual"): Promise<void> {
  const state = getState();
  if (state.running) {
    return;
  }

  state.running = true;
  let producedWork = false;

  try {
    producedWork = processBuilderDispatchConsumerOnce(reason) || producedWork;
    const ingestedBuilderOutputs = ingestBuilderOutputsFromChannel();
    const pendingBuilderOutputs = listPendingBuilderOutputs();
    const activeState = getActiveStateSnapshot();
    const openTasks = activeState.currentTasks.length ? activeState.currentTasks : listTasks().filter((task) => task.status === "open");
    const memories = activeState.knownAboutAlec;
    const awareness = activeState.awareness;
    const projectFocus = activeState.projectFocus;
    const topImprovement = getTopImprovementFocus();

    if (
      !openTasks.length &&
      !memories.length &&
      !pendingBuilderOutputs.length &&
      !activeState.pendingApprovals.length &&
      !topImprovement &&
      !(awareness?.currentFocus.length)
    ) {
      return;
    }

    recordAriEvent({
      type: "background_job_started",
      title: "Background review started",
      body: `ARI is scanning recent state${reason === "startup" ? " after startup" : ""}.`,
      autonomyLevel: "report",
      dedupeKey: `background:start:${new Date().toISOString().slice(0, 16)}`
    });

    producedWork = producedWork || ingestedBuilderOutputs.length > 0;
    if (pendingBuilderOutputs.length) {
      const processed = await processPendingBuilderOutputs();
      producedWork = producedWork || processed.length > 0;
    }

    producedWork = emitAwarenessSignals() || producedWork;
    producedWork = emitExecutionSignals() || producedWork;

    if (projectFocus?.majorBlocker && !hasRecentEvent(`project:blocker:${projectFocus.project.id}`, 120)) {
      recordAriEvent({
        type: "observation_generated",
        title: "Project progress is blocked",
        body: `${projectFocus.project.title}. Blocker: ${projectFocus.majorBlocker}`,
        autonomyLevel: "report",
        dedupeKey: `project:blocker:${projectFocus.project.id}`,
        metadata: { projectId: projectFocus.project.id }
      });
      producedWork = true;
    } else if (projectFocus?.nextStep && !hasRecentEvent(`project:next-step:${projectFocus.nextStep.id}`, 120)) {
      recordAriEvent({
        type: "suggestion_generated",
        title: "Project next step is ready",
        body: `${projectFocus.project.title}. Current milestone: ${projectFocus.currentMilestone?.title || "active"}. Next valid step: ${projectFocus.nextStep.title}`,
        autonomyLevel: "propose",
        dedupeKey: `project:next-step:${projectFocus.nextStep.id}`,
        metadata: { projectId: projectFocus.project.id, stepId: projectFocus.nextStep.id }
      });
      producedWork = true;
    }

    if (openTasks.length && !listPendingApprovals().find((approval) => approval.dedupeKey === `approval:focus-brief:${openTasks[0].id}`)) {
      await createFocusBriefApproval(openTasks);
      producedWork = true;
    }

    if (
      topImprovement &&
      topImprovement.reflection.total >= 2 &&
      topImprovement.status !== "verified" &&
      !hasRecentEvent(`suggestion:self-improvement:${topImprovement.capability}`, 90)
    ) {
      recordAriEvent({
        type: "suggestion_generated",
        title: `Advance ${topImprovement.capability} next`,
        body: `${topImprovement.whyItMatters} Smallest slice: ${topImprovement.smallestSlice}`,
        autonomyLevel: "propose",
        dedupeKey: `suggestion:self-improvement:${topImprovement.capability}`,
        metadata: { improvementId: topImprovement.id, priority: topImprovement.relativePriority, status: topImprovement.status }
      });
      producedWork = true;
    }

    if (openTasks.length > 1 && !hasRecentEvent("background:auto-task-snapshot", 180)) {
      const note = await saveCanonicalNote(
        `ARI Task Snapshot ${new Date().toISOString().slice(0, 16).replace("T", " ")}`,
        ["ARI generated this snapshot during a background cycle.", "", buildTaskSummary(openTasks, 5)].join("\n")
      );
      recordAriEvent({
        type: "note_saved",
        title: `ARI saved note "${note.title}"`,
        body: "A short task snapshot was stored in the canonical ARI spine.",
        autonomyLevel: "execute",
        metadata: { noteTitle: note.title }
      });
      recordAriEvent({
        type: "background_action_executed",
        title: "Background task snapshot saved",
        body: "ARI organized current working state into a reusable note and surfaced the result through the hub.",
        autonomyLevel: "execute",
        dedupeKey: "background:auto-task-snapshot"
      });
      producedWork = true;
    }

    if (!openTasks.length && memories.length && awareness?.mode === "steady" && !hasRecentEvent("observation:quiet-monitoring", 120)) {
      recordAriEvent({
        type: "observation_generated",
        title: "Quiet state detected",
        body: "ARI sees stored context about Alec and no urgent open work. The system is in quiet monitoring mode.",
        autonomyLevel: "report",
        dedupeKey: "observation:quiet-monitoring",
        metadata: { memoryCount: memories.length }
      });
      producedWork = true;
    }

    if (producedWork) {
      recordAriEvent({
        type: "background_job_completed",
        title: "Background review completed",
        body: "ARI emitted new observations, suggestions, or actions into the hub feed.",
        autonomyLevel: "report",
        dedupeKey: `background:done:${new Date().toISOString().slice(0, 16)}`
      });
    }
  } finally {
    state.running = false;
  }
}
