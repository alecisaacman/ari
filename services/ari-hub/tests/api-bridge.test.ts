import assert from "node:assert/strict";
import test from "node:test";

import { handleChatRequest, getActivitySnapshot } from "../src/core/api/services";
import { getDatabase } from "../src/core/db/database";
import { setupApiBackedRuntime, teardownIsolatedRuntime } from "./helpers";

test("hub canonical data flows through ari-api by default", async () => {
  await setupApiBackedRuntime("api-bridge");
  try {
    const first = await handleChatRequest({
      message: "My priority is converge ARI into the canonical repo through ari-api",
      source: "web"
    });
    const second = await handleChatRequest({
      message: "Create task verify the ari-api seam end to end",
      source: "web",
      conversationId: first.conversationId
    });

    assert.match(second.reply, /canonical ARI spine/i);

    const activity = await getActivitySnapshot();
    assert.equal(activity.activeState.currentPriorities[0]?.content.includes("ari-api"), true);
    assert.equal(activity.activeState.currentTasks.some((task) => /ari-api seam end to end/i.test(task.title)), true);

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
  } finally {
    teardownIsolatedRuntime();
  }
});
