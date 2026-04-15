import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { listWorkspaceFiles, readWorkspaceFile, resolveWorkspacePath, writeWorkspaceFile } from "../src/core/tools/workspace";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

test("workspace file tools stay inside sandbox", () => {
  const root = setupIsolatedRuntime("workspace");
  try {
    writeWorkspaceFile("notes/today.txt", "ship ARI");
    assert.equal(readWorkspaceFile("notes/today.txt"), "ship ARI");

    const entries = listWorkspaceFiles("notes");
    assert.equal(entries[0]?.path, "notes/today.txt");

    assert.throws(() => resolveWorkspacePath("../outside.txt"), /sandbox/i);
    assert.equal(fs.existsSync(path.join(root, "workspace", "notes", "today.txt")), true);
  } finally {
    teardownIsolatedRuntime();
  }
});
