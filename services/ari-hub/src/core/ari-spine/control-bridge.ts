import { isSubprocessBridgeMode, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

export type PauseState = {
  paused: boolean;
  reason: string | null;
  pausedAt: string | null;
};

export function isCanonicalPaused(): PauseState {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<PauseState>(["paused"])
    : requestAriApiSync<PauseState>("GET", "/paused");
}

export function pauseCanonical(reason: string = ""): PauseState {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<PauseState>(["pause", "--reason", reason])
    : requestAriApiSync<PauseState>("POST", "/pause", { body: { reason } });
}

export function resumeCanonical(): PauseState {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<PauseState>(["resume"])
    : requestAriApiSync<PauseState>("POST", "/resume");
}
