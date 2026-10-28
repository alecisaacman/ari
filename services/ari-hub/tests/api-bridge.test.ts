import assert from "node:assert/strict";
import test from "node:test";

import { getAriPanel, handleChatRequest } from "../src/core/api/services";
import { getDatabase } from "../src/core/db/database";
import { setupApiBackedRuntime, teardownIsolatedRuntime } from "./helpers";

test("hub talks to ARI's brain through ari-api by default", async () => {
  await setupApiBackedRuntime("api-bridge");
  try {
    const spend = await handleChatRequest({ message: "ARI spend" });
    assert.match(spend.reply ?? "", /this month/);
    assert.deepEqual(spend.conversation.map((line) => line.role), ["alec", "ari"]);

    const panel = await getAriPanel();
    assert.equal(panel.paused.paused, false);
    assert.equal(panel.conversations.hub.at(-1)?.text, spend.reply);
    assert.deepEqual(panel.openLoops, []);

    const localMemoryCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM memories").get() as {
        count: number;
      }
    ).count;
    assert.equal(localMemoryCount, 0);
  } finally {
    teardownIsolatedRuntime();
  }
});
