import { getConfig } from "@/src/core/config";
import { extractText, isDumpStale, readDumpRows, sendImessage } from "@/src/core/ari-spine/imessage-bridge";
import { getChannelCursor, getRecentMessages, setChannelCursor } from "@/src/core/memory/repository";
import { runTurn } from "@/src/core/agent/run-turn";

const CHANNEL = "imessage";
const CONVERSATION_ID = "imessage:self";
const ECHO_CHECK_LIMIT = 8;
const STALE_AFTER_MS = 5 * 60 * 1000;

export async function runImessageCycleOnce(dryRun = false): Promise<boolean> {
  const file = getConfig().imessageDumpPath;
  if (isDumpStale(file, STALE_AFTER_MS)) {
    return false;
  }

  const allRows = readDumpRows(file);
  const cursor = getChannelCursor(CHANNEL);

  if (cursor === null) {
    // Never seen this channel before: seed to the current tail instead of replaying all history.
    if (!dryRun && allRows.length) {
      setChannelCursor(CHANNEL, allRows[allRows.length - 1].rowid);
    }
    return false;
  }

  const rows = allRows.filter((row) => row.rowid > cursor);
  if (!rows.length) {
    return false;
  }

  const recentSent = new Set(
    getRecentMessages(CONVERSATION_ID, ECHO_CHECK_LIMIT)
      .filter((message) => message.role === "assistant")
      .map((message) => message.content)
  );

  let maxRowid = cursor;
  let producedWork = false;

  for (const row of rows) {
    maxRowid = Math.max(maxRowid, row.rowid);

    if (row.associatedMessageType) {
      // tapback reaction (Liked/Loved/etc.), not a real message
      continue;
    }

    const text = extractText(row.text, row.attributedBody);
    if (!text || recentSent.has(text)) {
      continue;
    }

    const result = await runTurn({ message: text, conversationId: CONVERSATION_ID, source: "imessage" });
    producedWork = true;

    if (result.reply && !dryRun) {
      if (sendImessage(row.chatIdentifier, result.reply)) {
        recentSent.add(result.reply);
      }
    }
  }

  if (!dryRun) {
    setChannelCursor(CHANNEL, maxRowid);
  }

  return producedWork;
}
