import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { listAriEvents } from "../src/core/agent/activity";
import { runBackgroundCycleOnce } from "../src/core/agent/background-runtime";
import { pauseCanonical, resumeCanonical } from "../src/core/ari-spine/control-bridge";
import { createTask } from "../src/core/memory/repository";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

const TESTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(TESTS_DIR, "..", "..", "..");
const FALLBACK_PYTHON = path.join(PROJECT_ROOT, ".venv", "bin", "python3.12");

test("background runtime skips its cycle while ARI is paused", async () => {
  const tempRoot = setupIsolatedRuntime("background-pause");
  if (!fs.existsSync(process.env.ARI_CANONICAL_PYTHON || "") && fs.existsSync(FALLBACK_PYTHON)) {
    process.env.ARI_CANONICAL_PYTHON = FALLBACK_PYTHON;
  }
  void tempRoot;

  try {
    createTask("Task that should produce background work");

    pauseCanonical("background-runtime test");
    await runBackgroundCycleOnce("manual");
    assert.equal(
      listAriEvents().some((event) => event.type === "background_job_started"),
      false,
      "background cycle ran work while paused"
    );

    resumeCanonical();
    await runBackgroundCycleOnce("manual");
    assert.equal(
      listAriEvents().some((event) => event.type === "background_job_started"),
      true,
      "background cycle did not run after resume"
    );
  } finally {
    teardownIsolatedRuntime();
  }
});
