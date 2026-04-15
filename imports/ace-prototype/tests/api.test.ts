import assert from "node:assert/strict";
import test from "node:test";

import { runBackgroundCycleOnce } from "../src/core/agent/background-runtime";
import {
  getActivitySnapshot,
  getHealthSnapshot,
  handleApprovalDecision,
  handleChatRequest,
  handleTriggerRequest,
  handleVoiceInputRequest,
  handleVoiceOutputRequest
} from "../src/core/api/services";
import { getDatabase } from "../src/core/db/database";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

test("chat, trigger, health, and voice fallback services work end to end", async () => {
  setupIsolatedRuntime("api");
  try {
    const health = await getHealthSnapshot();
    assert.equal(health.mode, "fallback");
    assert.equal(health.storage.dbReady, true);

    const chat = await handleChatRequest({ message: "Remember that I prefer concise replies", source: "web" });
    assert.equal(chat.conversationId.length > 0, true);

    await handleChatRequest({ message: "My priority is strengthen ARI memory", source: "web" });
    await handleChatRequest({ message: "I'm working on the active state surface", source: "web" });

    const saveNote = await handleChatRequest({ message: "Save note Bridge proof: canonical notes are now behind ARI", source: "web" });
    assert.match(saveNote.reply, /Saved note/i);

    const searchNote = await handleChatRequest({ message: "Find notes about Bridge proof", source: "web" });
    assert.match(searchNote.reply, /Bridge proof/i);

    const trigger = await handleTriggerRequest({ text: "List tasks" });
    assert.equal(trigger.status, "fallback");
    assert.equal(trigger.conversationId.length > 0, true);

    const createTask = await handleChatRequest({ message: "Create task review the hub activity model", source: "web" });
    assert.match(createTask.reply, /Created task/i);

    const localTaskCount = (
      getDatabase().prepare("SELECT COUNT(*) AS count FROM tasks").get() as {
        count: number;
      }
    ).count;
    assert.equal(localTaskCount, 0);

    await runBackgroundCycleOnce("manual");
    const activity = await getActivitySnapshot();
    assert.equal(activity.items.length > 0, true);
    assert.equal(activity.approvals.length > 0, true);
    assert.equal(activity.activeState.currentPriorities[0]?.content.includes("strengthen ARI memory"), true);
    assert.equal(activity.activeState.activeProjects[0]?.content.includes("active state surface"), true);
    assert.equal(Boolean(activity.activeState.awareness), true);
    assert.equal((activity.activeState.awareness?.currentFocus.length || 0) > 0, true);
    assert.equal(Boolean(activity.activeState.execution), true);
    assert.equal(Boolean(activity.activeState.projectFocus), true);
    assert.equal(Boolean(activity.activeState.projectFocus?.nextStep), true);
    assert.equal(activity.activeState.currentTasks.some((task) => /hub activity model/i.test(task.title)), true);

    const approvalResult = await handleApprovalDecision(activity.approvals[0].id, "approve");
    assert.equal(approvalResult.ok, true);

    const afterApproval = await getActivitySnapshot();
    assert.equal(afterApproval.items.some((item) => item.type === "action_executed"), true);
    assert.equal(afterApproval.items.some((item) => item.type === "approval_requested"), false);

    const formData = new FormData();
    formData.append("transcript", "List files");
    const voiceInput = await handleVoiceInputRequest(formData);
    assert.match(voiceInput.reply, /workspace|empty|Listed/i);

    const voiceOutput = await handleVoiceOutputRequest("hello");
    assert.equal("useBrowserTts" in voiceOutput, true);
  } finally {
    teardownIsolatedRuntime();
  }
});
