import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { getActivitySnapshot, handleCodingActionApprove, handleCodingActionCreate, handleCodingActionRun } from "../src/core/api/services";
import { getDatabase } from "../src/core/db/database";
import { setupApiBackedRuntime, teardownIsolatedRuntime } from "./helpers";

test("hub surfaces canonical coding execution through ari-api", async () => {
  const tempRoot = await setupApiBackedRuntime("operator-execution");
  const executionRoot = path.join(tempRoot, "execution-root");

  fs.writeFileSync(path.join(executionRoot, "operator-target.js"), "export const status = 'pending';\n", "utf8");
  fs.writeFileSync(
    path.join(executionRoot, "operator-check.test.mjs"),
    [
      "import assert from 'node:assert/strict';",
      "import fs from 'node:fs';",
      "import test from 'node:test';",
      "",
      "test('operator target is ready', () => {",
      "  const source = fs.readFileSync(new URL('./operator-target.js', import.meta.url), 'utf8');",
      "  assert.match(source, /ready/);",
      "});",
      ""
    ].join("\n"),
    "utf8"
  );

  try {
    const created = await handleCodingActionCreate({
      title: "Promote operator target to ready",
      summary: "Patch a file and verify it through node test.",
      operations: [
        {
          type: "patch",
          path: "operator-target.js",
          find: "pending",
          replace: "ready"
        }
      ],
      verifyCommand: "node --test operator-check.test.mjs",
      workingDirectory: ".",
      approvalRequired: false
    });

    const approved = await handleCodingActionApprove(created.action.id);
    assert.equal(approved.action.status, "approved");

    const run = await handleCodingActionRun(created.action.id);
    assert.equal(run.action.status, "verified");
    assert.equal(run.commandRun?.success, true);
    assert.equal(run.lastMutation?.path, "operator-target.js");

    const activity = await getActivitySnapshot();
    assert.equal(activity.activeState.codingExecution.currentAction?.id, created.action.id);
    assert.equal(activity.activeState.codingExecution.currentAction?.status, "verified");
    assert.match(activity.activeState.codingExecution.lastCommandRun?.command || "", /node --test/);
    assert.equal(activity.activeState.execution.completed.some((item) => item.kind === "coding_action"), true);

    const localTaskCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM tasks").get() as {
        count: number;
      }
    ).count;
    const localMemoryCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM memories").get() as {
        count: number;
      }
    ).count;
    assert.equal(localTaskCount, 0);
    assert.equal(localMemoryCount, 0);
    assert.match(fs.readFileSync(path.join(executionRoot, "operator-target.js"), "utf8"), /ready/);
  } finally {
    teardownIsolatedRuntime();
  }
});
