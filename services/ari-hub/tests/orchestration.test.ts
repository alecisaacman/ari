import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { runBackgroundCycleOnce } from "../src/core/agent/background-runtime";
import { refreshExecutionOutcomes } from "../src/core/agent/execution";
import { getTopRankedCapabilityGap, upsertImprovementProposal } from "../src/core/agent/self-improvement";
import { handleAlecDecision, handleApprovalDecision, handleOrchestrationDispatch, getActivitySnapshot, getOrchestrationSnapshot } from "../src/core/api/services";
import { runTurn } from "../src/core/agent/run-turn";
import { getDatabase } from "../src/core/db/database";
import { consumeOrchestrationDispatch, ingestBuilderOutputForProcessing, processPendingBuilderOutputs } from "../src/core/orchestration/processor";
import { createProjectPlan } from "../src/core/planning/project-planning";
import { readConsumedJson, readDispatchConsumerLog, readDispatchJson, readOutboxJson, setupIsolatedRuntime, teardownIsolatedRuntime, writeBuilderDrop, writeBuilderDropJson } from "./helpers";

test("builder outputs are auto-ingested, escalations pause processing, and the next-instruction channel updates", async () => {
  const root = setupIsolatedRuntime("orchestration", "manual");
  try {
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Minor update: activity feed labels are now clearer.");
    writeBuilderDrop(
      root,
      "002-escalate.txt",
      [
        "Repo layout tradeoff detected.",
        "This changes architecture and source-of-truth boundaries.",
        "Recommended action: decide whether ACE should own this logic or move it inward."
      ].join("\n")
    );
    writeBuilderDrop(root, "003-followup.txt", "Verification logs captured. Continue with the next smallest clean follow-up slice.");

    await runBackgroundCycleOnce("manual");

    const snapshot = await getOrchestrationSnapshot();
    assert.equal(snapshot.recent.length >= 3, true);
    assert.equal(snapshot.recent.some((record) => record.classification === "auto_pass"), true);
    assert.equal(snapshot.pendingEscalations.length >= 1, true);
    assert.equal(snapshot.pendingEscalations[0].escalationRequired, true);
    assert.equal(snapshot.control.paused, true);
    assert.match(snapshot.pendingEscalations[0].escalationPacket?.exactQuestionForAlec || "", /Alec/i);
    assert.equal(snapshot.recent.some((record) => record.status === "pending"), true);

    const processedRoot = path.join(root, "runtime", "orchestration", "processed");
    assert.equal(fs.readdirSync(processedRoot).length >= 3, true);

    const pausedInstruction = readOutboxJson(root, "latest-next-instruction.json");
    assert.equal(pausedInstruction.type, "next_instruction");
    assert.equal(pausedInstruction.dispatchStatus, "paused_for_escalation");
    assert.equal(pausedInstruction.instruction, "");

    const decisionResult = await handleAlecDecision(snapshot.pendingEscalations[0].id, "Approve the canonical-repo direction.");
    assert.equal(decisionResult.ok, true);

    await runBackgroundCycleOnce("manual");

    const afterDecision = await getOrchestrationSnapshot();
    assert.equal(afterDecision.pendingEscalations.length, 0);
    assert.equal(afterDecision.control.paused, false);
    assert.equal(afterDecision.recent.some((record) => record.status === "pending"), false);

    const resumedInstruction = readOutboxJson(root, "latest-next-instruction.json");
    assert.equal(typeof resumedInstruction.instruction, "string");
    assert.notEqual(resumedInstruction.instruction, "");
    assert.equal(resumedInstruction.dispatchStatus, "awaiting_alec_send");

    const afterDecisionSnapshot = await getOrchestrationSnapshot();
    assert.equal(afterDecisionSnapshot.dispatch.latestStatus, "awaiting_alec_send");
    assert.equal(afterDecisionSnapshot.dispatch.stateLabel, "waiting");

    const activity = await getActivitySnapshot();
    assert.equal(activity.items.some((item) => item.type === "orchestration_received"), true);
    assert.equal(activity.items.some((item) => item.type === "orchestration_classified"), true);
    assert.equal(activity.items.some((item) => item.type === "orchestration_next_instruction"), true);
    assert.equal(activity.items.some((item) => item.type === "orchestration_escalation_requested"), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("assisted mode waits for Alec confirmation before dispatching to the builder channel", async () => {
  const root = setupIsolatedRuntime("orchestration-assisted", "assisted");
  try {
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Continue with the next smallest memory slice.");
    await runBackgroundCycleOnce("manual");

    const beforeDispatch = await getOrchestrationSnapshot();
    assert.equal(beforeDispatch.control.mode, "assisted");
    assert.equal(beforeDispatch.dispatch.latestStatus, "awaiting_alec_confirm");
    assert.equal(fs.existsSync(path.join(root, "runtime", "orchestration", "dispatch", "latest-dispatch.json")), false);

    const dispatchResult = await handleOrchestrationDispatch(beforeDispatch.latest!.id);
    assert.equal(dispatchResult.ok, true);

    const dispatchFile = readDispatchJson(root, "latest-dispatch.json");
    assert.equal(dispatchFile.type, "builder_dispatch");
    assert.equal(typeof dispatchFile.dispatchRecordId, "string");
    assert.equal(dispatchFile.dispatchStatus, "dispatched_to_builder");

    const afterDispatch = await getOrchestrationSnapshot();
    assert.equal(afterDispatch.dispatch.latestStatus, "dispatched_to_builder");
    assert.equal(afterDispatch.dispatch.stateLabel, "continuing");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("builder consumer automatically picks up dispatched instructions on the next cycle without duplicate consumption", async () => {
  const root = setupIsolatedRuntime("orchestration-builder-consumer", "assisted");
  try {
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Continue with the next smallest clean operator slice.");
    await runBackgroundCycleOnce("manual");

    const beforeDispatch = await getOrchestrationSnapshot();
    await handleOrchestrationDispatch(beforeDispatch.latest!.id);

    let snapshot = await getOrchestrationSnapshot();
    assert.equal(snapshot.dispatch.latestStatus, "dispatched_to_builder");

    await runBackgroundCycleOnce("manual");

    snapshot = await getOrchestrationSnapshot();
    assert.equal(snapshot.dispatch.latestStatus, "consumed_by_builder");
    const consumedFile = readConsumedJson(root, "latest-consumed.json");
    assert.equal(consumedFile.dispatchStatus, "consumed_by_builder");
    assert.equal(consumedFile.consumer, "ari-builder-consumer");

    const logEntries = readDispatchConsumerLog(root);
    assert.equal(logEntries.length, 1);
    assert.equal(logEntries[0]?.type, "builder_dispatch_consumed");

    await runBackgroundCycleOnce("manual");
    assert.equal(readDispatchConsumerLog(root).length, 1);

    const activity = await getActivitySnapshot();
    assert.equal(activity.activeState.operatorChannels.channels.some((channel) => channel.id === "builder_dispatch_consumer" && channel.status !== "blocked"), true);
    assert.equal(activity.activeState.operatorChannels.executionOpportunities.some((line) => /shortcut|builder/i.test(line)), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("auto mode dispatches safe instructions automatically and stops at one handoff", async () => {
  const root = setupIsolatedRuntime("orchestration-auto", "auto");
  try {
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Continue with the next smallest clean follow-up slice.");
    writeBuilderDrop(root, "002-pass.txt", "Implementation notes are stable. Move to the next verification step.");

    await runBackgroundCycleOnce("manual");

    const snapshot = await getOrchestrationSnapshot();
    assert.equal(snapshot.control.mode, "auto");
    assert.equal(["auto_dispatched", "consumed_by_builder"].includes(snapshot.dispatch.latestStatus), true);
    assert.equal(snapshot.dispatch.stateLabel, "continuing");
    assert.equal(snapshot.recent.some((record) => record.status === "pending"), true);

    const dispatchFile = readDispatchJson(root, "latest-dispatch.json");
    assert.equal(dispatchFile.dispatchStatus, "auto_dispatched");
    assert.equal(typeof dispatchFile.instruction, "string");
    assert.notEqual(dispatchFile.instruction, "");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("self-improvement execution graph links dispatch, consumption, and verification explicitly", async () => {
  const root = setupIsolatedRuntime("orchestration-improvement-graph", "assisted");
  try {
    await runTurn({ message: "I want you to control the interface directly." });
    let activity = await getActivitySnapshot();
    const improvementId = activity.activeState.topImprovement?.id;
    assert.equal(typeof improvementId, "string");
    await handleApprovalDecision(activity.approvals[0].id, "approve");

    ingestBuilderOutputForProcessing("Queue the next builder slice for interface control.", "codex", {
      linkedImprovementIds: [improvementId as string],
      linkageMode: "explicit"
    });
    await processPendingBuilderOutputs();

    const snapshot = await getOrchestrationSnapshot();
    await handleOrchestrationDispatch(snapshot.latest!.id);
    const consumed = consumeOrchestrationDispatch("local-builder");
    assert.equal(consumed.consumer, "local-builder");
    const consumedFile = readConsumedJson(root, "latest-consumed.json");
    assert.equal(consumedFile.dispatchStatus, "consumed_by_builder");

    writeBuilderDropJson(root, "improvement-result.json", {
      rawOutput: "Implemented the interface-control bridge and verified it with tests.",
      source: "codex",
      parentOrchestrationId: snapshot.latest!.id,
      linkedImprovementIds: [improvementId as string],
      verificationSignal: "verified"
    });

    await runBackgroundCycleOnce("manual");
    activity = await getActivitySnapshot();
    assert.equal(typeof activity.activeState.improvementLifecycle[0]?.dispatchRecordId, "string");
    assert.equal(activity.activeState.improvementLifecycle[0]?.dispatchOrchestrationId, snapshot.latest!.id);
    assert.equal(activity.activeState.improvementLifecycle[0]?.consumedAt !== undefined, true);
    assert.equal(activity.activeState.improvementLifecycle[0]?.verificationEvidence, "explicit");
    assert.equal(activity.activeState.improvementLifecycle[0]?.status, "verified");
    assert.equal(activity.activeState.execution.completed.some((item) => item.kind === "improvement"), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("execution tracking marks stalled dispatches as blocked instead of leaving them silent", async () => {
  const root = setupIsolatedRuntime("orchestration-stalled-dispatch", "assisted");
  try {
    process.env.ARI_EXECUTION_STALL_MINUTES = "0";
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Continue with the next smallest execution slice.");
    await runBackgroundCycleOnce("manual");

    const snapshot = await getOrchestrationSnapshot();
    await handleOrchestrationDispatch(snapshot.latest!.id);
    await runBackgroundCycleOnce("manual");

    const activity = await getActivitySnapshot();
    assert.equal(activity.activeState.execution.blocked.some((item) => item.kind === "dispatch"), true);
    assert.equal(activity.items.some((item) => /blocked/i.test(item.title)), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("active state exposes available channels, blocked channels, and the current autonomy blocker", async () => {
  const root = setupIsolatedRuntime("orchestration-channel-map", "manual");
  try {
    const activity = await getActivitySnapshot();
    const channels = activity.activeState.operatorChannels.channels;
    assert.equal(channels.some((channel) => channel.id === "shortcut_entry" && channel.status === "available"), true);
    assert.equal(channels.some((channel) => channel.id === "notification_delivery" && channel.status === "blocked"), true);
    assert.equal(activity.activeState.operatorChannels.majorBlocker?.id, "notification_delivery");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("coordination state is canonically owned while ACE local coordination tables stay unused", async () => {
  const root = setupIsolatedRuntime("coordination-convergence", "assisted");
  try {
    const project = createProjectPlan("Converge the remaining ARI coordination runtime inward");
    const proposal = getTopRankedCapabilityGap("I want you to control the interface directly.");
    assert.notEqual(proposal, null);
    const improvement = upsertImprovementProposal(proposal!);

    ingestBuilderOutputForProcessing("Tests passed. Continue with the next smallest clean follow-up slice.", "codex", {
      linkedImprovementIds: [improvement.id],
      linkageMode: "explicit"
    });
    await processPendingBuilderOutputs();

    const snapshot = await getOrchestrationSnapshot();
    assert.equal(snapshot.recent.length > 0, true);
    await handleOrchestrationDispatch(snapshot.latest!.id);
    consumeOrchestrationDispatch("local-builder");

    writeBuilderDropJson(root, "coordination-result.json", {
      rawOutput: "Completed the canonical coordination runtime slice and verified the behavior with tests.",
      source: "codex",
      parentOrchestrationId: snapshot.latest!.id,
      linkedImprovementIds: [improvement.id],
      verificationSignal: "verified"
    });

    await runBackgroundCycleOnce("manual");
    refreshExecutionOutcomes();
    const activity = await getActivitySnapshot();

    assert.equal(activity.activeState.improvementLifecycle.length > 0, true);
    assert.equal(["completed", "verified"].includes(activity.activeState.improvementLifecycle[0]?.status || ""), true);
    assert.equal(
      [activity.activeState.improvementLifecycle[0]?.completionEvidence, activity.activeState.improvementLifecycle[0]?.verificationEvidence].includes("explicit"),
      true
    );
    assert.equal(activity.activeState.projectFocus?.project.id, project.project.id);
    assert.equal(activity.activeState.projectFocus?.nextStep !== undefined, true);

    const database = getDatabase();
    const localCounts = {
      selfImprovements: (database.prepare("SELECT COUNT(*) AS count FROM self_improvements").get() as { count: number }).count,
      orchestrationRecords: (database.prepare("SELECT COUNT(*) AS count FROM orchestration_records").get() as { count: number }).count,
      dispatchRecords: (database.prepare("SELECT COUNT(*) AS count FROM builder_dispatch_records").get() as { count: number }).count,
      executionOutcomes: (database.prepare("SELECT COUNT(*) AS count FROM execution_outcomes").get() as { count: number }).count,
      projects: (database.prepare("SELECT COUNT(*) AS count FROM projects").get() as { count: number }).count,
      projectMilestones: (database.prepare("SELECT COUNT(*) AS count FROM project_milestones").get() as { count: number }).count,
      projectSteps: (database.prepare("SELECT COUNT(*) AS count FROM project_steps").get() as { count: number }).count
    };

    assert.deepEqual(localCounts, {
      selfImprovements: 0,
      orchestrationRecords: 0,
      dispatchRecords: 0,
      executionOutcomes: 0,
      projects: 0,
      projectMilestones: 0,
      projectSteps: 0
    });
  } finally {
    teardownIsolatedRuntime();
  }
});
