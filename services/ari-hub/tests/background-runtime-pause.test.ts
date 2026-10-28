import assert from "node:assert/strict";
import test from "node:test";

import { runBackgroundCycleOnce } from "../src/core/agent/background-runtime";
import { pauseCanonical, resumeCanonical } from "../src/core/ari-spine/control-bridge";
import { getOrchestrationSnapshot } from "../src/core/api/services";
import { setupIsolatedRuntime, teardownIsolatedRuntime, writeBuilderDrop } from "./helpers";

test("background runtime skips its cycle while ARI is paused", async () => {
  const root = setupIsolatedRuntime("background-pause");

  try {
    writeBuilderDrop(root, "001-pass.txt", "Tests passed. Continue with the next smallest execution slice.");

    pauseCanonical("background-runtime test");
    await runBackgroundCycleOnce("manual");
    assert.equal((await getOrchestrationSnapshot()).latest, null, "background cycle ran work while paused");

    resumeCanonical();
    await runBackgroundCycleOnce("manual");
    assert.notEqual((await getOrchestrationSnapshot()).latest, null, "background cycle did not run after resume");
  } finally {
    teardownIsolatedRuntime();
  }
});
