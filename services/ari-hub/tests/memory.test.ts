import assert from "node:assert/strict";
import test from "node:test";

import { runTurn } from "../src/core/agent/run-turn";
import { closeDatabase, getDatabase } from "../src/core/db/database";
import { createTask, listTasks, retrieveMemories, saveMemory } from "../src/core/memory/repository";
import { getActiveStateSnapshot, retrieveMemoryContext } from "../src/core/memory/spine";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

test("memory and tasks persist across database reopen", () => {
  setupIsolatedRuntime("memory");
  try {
    saveMemory("note", "Launch checklist", "ship auth and tests");
    createTask("verify LAN access");

    closeDatabase();

    const memories = retrieveMemories("launch");
    const tasks = listTasks();

    assert.equal(memories.length, 1);
    assert.equal(memories[0]?.title, "Launch checklist");
    assert.equal(tasks.length, 1);
    assert.equal(tasks[0]?.title, "verify LAN access");
  } finally {
    teardownIsolatedRuntime();
  }
});

test("structured memory and active state persist across restarts", async () => {
  setupIsolatedRuntime("memory-state");
  try {
    const firstTurn = await runTurn({ message: "My priority is strengthen ARI memory and state visibility" });
    await runTurn({
      message: "I'm working on the ACE active state hub",
      conversationId: firstTurn.conversationId
    });
    await runTurn({
      message: "My operating principle is preserve one canon",
      conversationId: firstTurn.conversationId
    });

    let state = getActiveStateSnapshot();
    let context = retrieveMemoryContext("state visibility");
    const localMemoryCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM memories").get() as {
        count: number;
      }
    ).count;
    const localAwarenessCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM awareness_snapshots").get() as {
        count: number;
      }
    ).count;

    assert.equal(state.currentPriorities[0]?.content.includes("strengthen ARI memory"), true);
    assert.equal(state.activeProjects[0]?.content.includes("ACE active state hub"), true);
    assert.equal(state.knownAboutAlec.some((memory) => memory.type === "operating_principle"), true);
    assert.equal(context.summaryLines.some((line) => line.includes("Current priority")), true);
    assert.equal(localMemoryCount, 0);
    assert.equal(Boolean(state.awareness?.summary), true);
    assert.equal(localAwarenessCount, 0);

    closeDatabase();

    state = getActiveStateSnapshot();
    context = retrieveMemoryContext("state visibility");

    assert.equal(state.currentPriorities[0]?.content.includes("strengthen ARI memory"), true);
    assert.equal(state.activeProjects[0]?.content.includes("ACE active state hub"), true);
    assert.equal(context.workingStateSignals.length > 0, true);
  } finally {
    teardownIsolatedRuntime();
  }
});
