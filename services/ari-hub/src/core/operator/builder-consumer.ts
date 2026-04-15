import fs from "node:fs";
import path from "node:path";

import { recordAriEvent } from "@/src/core/agent/activity";
import { getConfig } from "@/src/core/config";
import { readLatestConsumedEnvelope, readLatestDispatchEnvelope } from "@/src/core/orchestration/channels";
import { consumeOrchestrationDispatch } from "@/src/core/orchestration/processor";

function appendConsumerLog(entry: Record<string, unknown>): void {
  const config = getConfig();
  fs.mkdirSync(path.dirname(config.orchestrationDispatchLogPath), { recursive: true });
  fs.appendFileSync(config.orchestrationDispatchLogPath, `${JSON.stringify(entry)}\n`, "utf8");
}

export function processBuilderDispatchConsumerOnce(reason: "startup" | "interval" | "manual"): boolean {
  const config = getConfig();
  if (config.builderConsumerMode === "off") {
    return false;
  }

  const latestDispatch = readLatestDispatchEnvelope();
  if (!latestDispatch) {
    return false;
  }

  const latestConsumed = readLatestConsumedEnvelope();
  if (latestConsumed?.dispatchRecordId === latestDispatch.dispatchRecordId) {
    return false;
  }

  const consumed = consumeOrchestrationDispatch(config.builderConsumerName);
  appendConsumerLog({
    type: "builder_dispatch_consumed",
    reason,
    dispatchRecordId: consumed.dispatchRecordId,
    orchestrationId: consumed.orchestrationId,
    consumer: consumed.consumer,
    consumedAt: consumed.consumedAt
  });

  recordAriEvent({
    type: "action_executed",
    title: "Builder consumer picked up the next instruction",
    body: `${consumed.consumer} picked up the local builder handoff and is now waiting for builder output.`,
    autonomyLevel: "execute",
    metadata: {
      orchestrationId: consumed.orchestrationId,
      dispatchRecordId: consumed.dispatchRecordId,
      consumer: consumed.consumer
    }
  });

  return true;
}
