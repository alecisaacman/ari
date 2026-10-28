import { listPendingBuilderOutputs } from "@/src/core/orchestration/repository";
import { ingestBuilderOutputsFromChannel, processPendingBuilderOutputs } from "@/src/core/orchestration/processor";
import { processBuilderDispatchConsumerOnce } from "@/src/core/operator/builder-consumer";
import { isCanonicalPaused } from "@/src/core/ari-spine/control-bridge";

type BackgroundState = {
  started: boolean;
  running: boolean;
  timer: NodeJS.Timeout | null;
};

declare global {
  var __ariBackgroundState: BackgroundState | undefined;
}

function getState(): BackgroundState {
  if (!globalThis.__ariBackgroundState) {
    globalThis.__ariBackgroundState = {
      started: false,
      running: false,
      timer: null
    };
  }

  return globalThis.__ariBackgroundState;
}

function getIntervalMs(): number {
  const raw = Number(process.env.ARI_BACKGROUND_INTERVAL_MS || 45000);
  return Number.isFinite(raw) && raw >= 5000 ? raw : 45000;
}

export function ensureBackgroundRuntime(): void {
  const state = getState();
  if (state.started) {
    return;
  }

  state.started = true;
  state.timer = setInterval(() => {
    void runBackgroundCycleOnce("interval");
  }, getIntervalMs());
  state.timer.unref();
  void runBackgroundCycleOnce("startup");
}

export function stopBackgroundRuntime(): void {
  const state = getState();
  if (state.timer) {
    clearInterval(state.timer);
  }

  state.started = false;
  state.running = false;
  state.timer = null;
}

export async function runBackgroundCycleOnce(reason: "startup" | "interval" | "manual" = "manual"): Promise<void> {
  // The hub only moves builder outputs through their review queue. Noticing,
  // suggesting, and deciding are ARI's: its signal engine, alerts, and brain.
  const state = getState();
  if (state.running) {
    return;
  }

  if (isCanonicalPaused().paused) {
    return;
  }

  state.running = true;
  try {
    processBuilderDispatchConsumerOnce(reason);
    ingestBuilderOutputsFromChannel();
    if (listPendingBuilderOutputs().length) {
      await processPendingBuilderOutputs();
    }
  } finally {
    state.running = false;
  }
}
