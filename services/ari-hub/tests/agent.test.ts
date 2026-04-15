import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { runTurn } from "../src/core/agent/run-turn";
import { getActivitySnapshot, handleApprovalDecision } from "../src/core/api/services";
import { detectRankedCapabilityGaps } from "../src/core/agent/self-improvement";
import { ingestBuilderOutputForProcessing, processPendingBuilderOutputs } from "../src/core/orchestration/processor";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

test("agent handles deterministic note, task, file, and delegation flows", async () => {
  const root = setupIsolatedRuntime("agent");
  try {
    const noteTurn = await runTurn({ message: "Save note Daily brief: ship the private auth flow" });
    assert.match(noteTurn.reply, /Saved note/i);

    const taskTurn = await runTurn({ message: "Create task verify the trigger endpoint", conversationId: noteTurn.conversationId });
    assert.match(taskTurn.reply, /Created task/i);

    const writeTurn = await runTurn({
      message: "Write file notes/today.txt: ARI is online",
      conversationId: noteTurn.conversationId
    });
    assert.match(writeTurn.reply, /Wrote notes\/today\.txt/i);
    assert.equal(fs.existsSync(path.join(root, "workspace", "notes", "today.txt")), true);

    const delegateTurn = await runTurn({
      message: "Delegate to planner map the next set of improvements",
      conversationId: noteTurn.conversationId
    });
    assert.equal(delegateTurn.delegations.length, 1);
    assert.match(delegateTurn.reply, /Delegation plan created/i);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("agent explains ARI and ACE consistently in fallback mode", async () => {
  setupIsolatedRuntime("identity");
  try {
    const turn = await runTurn({ message: "What is the difference between ARI and ACE?" });
    assert.match(turn.reply, /ARI is the brain/i);
    assert.match(turn.reply, /ACE is the access layer/i);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("agent uses structured memory for direct fallback guidance", async () => {
  setupIsolatedRuntime("memory-guidance");
  try {
    const turn = await runTurn({ message: "My priority is finish the memory spine" });
    const followUp = await runTurn({
      message: "What should I focus on?",
      conversationId: turn.conversationId
    });
    assert.match(followUp.reply, /Current priority/i);
    assert.match(followUp.reply, /finish the memory spine/i);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("agent can break a goal into a dependency-aware project path", async () => {
  setupIsolatedRuntime("project-plan");
  try {
    const turn = await runTurn({ message: "Plan project turn ARI into a strategic execution system" });
    assert.match(turn.reply, /Project focus established/i);
    assert.match(turn.reply, /Next valid step/i);

    const activity = await getActivitySnapshot();
    assert.equal(Boolean(activity.activeState.projectFocus), true);
    assert.equal(Boolean(activity.activeState.projectFocus?.currentMilestone), true);
    assert.equal(Boolean(activity.activeState.projectFocus?.nextStep), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("agent turns capability gaps into real improvement proposals", async () => {
  setupIsolatedRuntime("capability-gap");
  try {
    const first = await runTurn({ message: "I want you to control the interface directly." });
    assert.match(first.reply, /direct interface control/i);
    assert.match(first.reply, /Approval queued/i);

    const second = await runTurn({
      message: "You should be able to click and scroll the interface yourself.",
      conversationId: first.conversationId
    });
    assert.match(second.reply, /Next move: Queue the interface-control bridge now/i);

    const activity = await getActivitySnapshot();
    assert.equal(activity.approvals.length, 1);
    assert.equal(activity.approvals[0]?.title, "Queue interface-control bridge");
    assert.equal(activity.items.some((item) => item.type === "suggestion_generated" && /interface control/i.test(item.title)), true);
    assert.equal(activity.activeState.topImprovement?.capability, "interface-control");
    assert.equal(activity.activeState.topImprovement?.status, "proposed");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("self-improvement ranking selects the strongest next capability slice", () => {
  setupIsolatedRuntime("improvement-ranking");
  try {
    const ranked = detectRankedCapabilityGaps(
      "I want you to control the interface directly and notify me on my phone when approvals are waiting."
    );
    assert.equal(ranked.length >= 2, true);
    assert.equal(ranked[0]?.capability, "interface-control");
    assert.equal(ranked[0]?.relativePriority, "highest");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("self-improvement lifecycle advances from proposal to verification", async () => {
  setupIsolatedRuntime("improvement-lifecycle");
  try {
    await runTurn({ message: "You should be able to click and scroll the interface yourself." });
    let activity = await getActivitySnapshot();
    assert.equal(activity.activeState.topImprovement?.status, "proposed");

    await handleApprovalDecision(activity.approvals[0].id, "approve");
    activity = await getActivitySnapshot();
    assert.equal(activity.activeState.topImprovement?.status, "queued");

    ingestBuilderOutputForProcessing("Implemented the interface-control bridge for the ACE interface.", "codex");
    await processPendingBuilderOutputs();
    activity = await getActivitySnapshot();
    assert.equal(activity.activeState.topImprovement?.status, "completed");

    ingestBuilderOutputForProcessing("Verified the interface-control bridge. Tests passed.", "codex");
    await processPendingBuilderOutputs();
    activity = await getActivitySnapshot();
    assert.equal(activity.activeState.improvementLifecycle[0]?.status, "verified");
  } finally {
    teardownIsolatedRuntime();
  }
});
