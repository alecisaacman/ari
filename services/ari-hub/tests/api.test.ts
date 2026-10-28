import assert from "node:assert/strict";
import test from "node:test";

import {
  getAriPanel,
  getHealthSnapshot,
  handleChatRequest,
  handleTriggerRequest,
  handleVoiceInputRequest
} from "../src/core/api/services";
import { getDatabase } from "../src/core/db/database";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

// These messages are commands ARI decides without a model, so no API key is needed
// and nothing is billed. Anything else would go to ARI's brain the same way.

test("hub chat, trigger, and voice all reach ARI's one conversation", async () => {
  setupIsolatedRuntime("api");
  try {
    const health = await getHealthSnapshot();
    assert.equal(health.mode, "ari");
    assert.equal(health.voice.serverTranscription, false);

    const spend = await handleChatRequest({ message: "ARI spend" });
    assert.match(spend.reply ?? "", /\$0\.00 of \$10\.00 this month/);

    const trigger = await handleTriggerRequest({ text: "ARI budget 12" });
    assert.equal(trigger.status, "ok");
    assert.match(trigger.reply ?? "", /Monthly budget set to \$12\.00/);

    const formData = new FormData();
    formData.append("transcript", "ARI stop");
    const voice = await handleVoiceInputRequest(formData);
    assert.match(voice.reply ?? "", /^Paused\./);

    const panel = await getAriPanel();
    assert.equal(panel.paused.paused, true);
    assert.equal(panel.spend.budgetUsd, 12);
    assert.deepEqual(
      panel.conversations.hub.filter((line) => line.role === "alec").map((line) => line.text),
      ["ARI spend", "ARI budget 12", "ARI stop"]
    );

    const resumed = await handleChatRequest({ message: "ARI resume" });
    assert.match(resumed.reply ?? "", /^Resumed\./);

    // The hub keeps none of it: ARI's records are the only copy.
    const localMessages = (getDatabase().prepare("SELECT COUNT(*) AS count FROM messages").get() as { count: number }).count;
    assert.equal(localMessages, 0);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("voice input needs a transcript from the browser", async () => {
  setupIsolatedRuntime("api-voice");
  try {
    await assert.rejects(handleVoiceInputRequest(new FormData()), /transcript is required/);
  } finally {
    teardownIsolatedRuntime();
  }
});
