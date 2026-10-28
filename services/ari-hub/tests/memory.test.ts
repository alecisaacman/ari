import assert from "node:assert/strict";
import test from "node:test";

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
