import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { runBackgroundCycleOnce } from "../src/core/agent/background-runtime";
import { pauseCanonical, resumeCanonical } from "../src/core/ari-spine/control-bridge";
import { runImessageCycleOnce } from "../src/core/agent/imessage-cycle";
import { appendMessage, ensureConversation, getChannelCursor, getRecentMessages } from "../src/core/memory/repository";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

const CHANNEL = "imessage";
const CONVERSATION_ID = "imessage:self";
// Deliberately not a real number/contact: these tests exercise runImessageCycleOnce()
// without dryRun, which calls the real sendImessage(). A fake identifier ensures any
// AppleScript invocation fails to resolve a buddy and never actually delivers anything.
const CHAT_IDENTIFIER = "+10000000000";

type DumpRowInput = {
  rowid: number;
  text: string;
  chatIdentifier?: string;
  assocType?: number;
};

function hex(value: string): string {
  return Buffer.from(value, "latin1").toString("hex");
}

function writeDumpFile(filePath: string, rows: DumpRowInput[]): void {
  const lines = rows.map(
    (row) =>
      `${row.rowid}|${hex(row.text)}||${Date.now()}|${row.chatIdentifier ?? CHAT_IDENTIFIER}|${row.assocType ?? 0}`
  );
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, lines.join("\n") + "\n", "utf8");
}

function useDumpFile(tempRoot: string): string {
  const dumpFile = path.join(tempRoot, "imessage-dump.tsv");
  process.env.ARI_IMESSAGE_DUMP_PATH = dumpFile;
  return dumpFile;
}

test("the first cycle for a channel seeds the cursor to the tail instead of replaying historical backlog", async () => {
  const root = setupIsolatedRuntime("imessage-seed");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [
      { rowid: 1, text: "Some old historical self-thread note" },
      { rowid: 2, text: "Another old historical self-thread note" },
      { rowid: 3, text: "Yet another old historical self-thread note" }
    ]);

    const producedWork = await runImessageCycleOnce();

    assert.equal(producedWork, false);
    assert.equal(getChannelCursor(CHANNEL), 3);
    assert.equal(getRecentMessages(CONVERSATION_ID, 10).length, 0);
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("a fresh inbound message reaches runTurn, produces a reply, and advances the cursor", async () => {
  const root = setupIsolatedRuntime("imessage-fresh");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 1, text: "seed row" }]);
    await runImessageCycleOnce();
    assert.equal(getChannelCursor(CHANNEL), 1, "seeding cycle did not run");

    writeDumpFile(dumpFile, [
      { rowid: 1, text: "seed row" },
      { rowid: 2, text: "Create task call the dentist" }
    ]);

    const producedWork = await runImessageCycleOnce();

    assert.equal(producedWork, true);
    assert.equal(getChannelCursor(CHANNEL), 2);
    const messages = getRecentMessages(CONVERSATION_ID, 10);
    assert.ok(messages.some((message) => message.role === "assistant" && /Created task/i.test(message.content)));
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("a message matching a recent assistant reply is skipped as an echo, but the cursor still advances past it", async () => {
  const root = setupIsolatedRuntime("imessage-echo");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 4, text: "seed row" }]);
    await runImessageCycleOnce();
    assert.equal(getChannelCursor(CHANNEL), 4, "seeding cycle did not run");

    const conversationId = ensureConversation(CONVERSATION_ID, "imessage");
    appendMessage(conversationId, "assistant", "Echo content from ARI");

    writeDumpFile(dumpFile, [
      { rowid: 4, text: "seed row" },
      { rowid: 5, text: "Echo content from ARI" }
    ]);

    const producedWork = await runImessageCycleOnce();

    assert.equal(producedWork, false);
    assert.equal(getChannelCursor(CHANNEL), 5);
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("a tapback reaction row is skipped without reaching runTurn", async () => {
  const root = setupIsolatedRuntime("imessage-tapback");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 1, text: "seed row" }]);
    await runImessageCycleOnce();
    assert.equal(getChannelCursor(CHANNEL), 1, "seeding cycle did not run");

    writeDumpFile(dumpFile, [
      { rowid: 1, text: "seed row" },
      { rowid: 2, text: "Loved “Hey”", assocType: 2000 }
    ]);

    const producedWork = await runImessageCycleOnce();

    assert.equal(producedWork, false);
    assert.equal(getChannelCursor(CHANNEL), 2);
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("dryRun runs the turn but never advances the cursor or sends a reply", async () => {
  const root = setupIsolatedRuntime("imessage-dry-run");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 1, text: "seed row" }]);
    await runImessageCycleOnce();
    assert.equal(getChannelCursor(CHANNEL), 1, "seeding cycle did not run");

    writeDumpFile(dumpFile, [
      { rowid: 1, text: "seed row" },
      { rowid: 3, text: "Create task draft the weekly review" }
    ]);

    const producedWork = await runImessageCycleOnce(true);

    assert.equal(producedWork, true);
    assert.equal(getChannelCursor(CHANNEL), 1);
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("a stale dump file is ignored entirely, even before the channel has ever been seeded", async () => {
  const root = setupIsolatedRuntime("imessage-stale");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 4, text: "Create task this should not run" }]);
    const old = new Date(Date.now() - 10 * 60 * 1000);
    fs.utimesSync(dumpFile, old, old);

    const producedWork = await runImessageCycleOnce();

    assert.equal(producedWork, false);
    assert.equal(getChannelCursor(CHANNEL), null);
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});

test("the background cycle skips the iMessage cycle while ARI is paused, and seeds (without replaying) after resume", async () => {
  const root = setupIsolatedRuntime("imessage-paused");
  const dumpFile = useDumpFile(root);
  try {
    writeDumpFile(dumpFile, [{ rowid: 6, text: "Create task should wait for resume" }]);

    pauseCanonical("imessage-cycle test");
    await runBackgroundCycleOnce("manual");
    assert.equal(getChannelCursor(CHANNEL), null, "iMessage cycle ran while ARI was paused");

    resumeCanonical();
    await runBackgroundCycleOnce("manual");
    assert.equal(getChannelCursor(CHANNEL), 6, "iMessage cycle did not seed after resume");
    assert.equal(
      getRecentMessages(CONVERSATION_ID, 10).length,
      0,
      "first cycle after resume should seed, not replay, the backlog"
    );
  } finally {
    delete process.env.ARI_IMESSAGE_DUMP_PATH;
    teardownIsolatedRuntime();
  }
});
