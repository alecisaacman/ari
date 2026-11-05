import { AriApiError, isSubprocessBridgeMode, requestAriApi, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

// The hub has no brain of its own. It shows ARI's control panel and carries
// Alec's messages to ARI's one brain, the same one iMessage reaches.

export type ExchangeLine = { role: "alec" | "ari"; text: string };

export type BrainPanel = {
  generatedAt: string;
  paused: { paused: boolean; reason: string | null; pausedAt: string | null };
  today: {
    priorities: string[];
    win_condition: string;
    stress: number | null;
    next_action: string;
  } | null;
  week: { outcomes: string[]; cannot_drift: string[]; blockers: string[] } | null;
  openLoops: Array<{
    id: string;
    title: string;
    kind: string;
    priority: string;
    notes: string;
    openedAt: string;
    lastTouchedAt: string | null;
  }>;
  hubTasks: Array<{ id: number; title: string; notes: string }>;
  reminders: Array<{
    id: string;
    text: string;
    remind_at: string;
    status: string;
    loop_id: string | null;
    delivered_by?: string;
  }>;
  apple?: { connected: boolean; error: string | null };
  builds?: Array<{ id: string; title: string; why: string; brief: string; skill_id: string | null; status: string; proposed_at: string; branch?: string | null; result?: string | null }>;
  getDone?: Array<{ id: string; title: string; due?: string; notes?: string }>;
  calendarToday?: Array<{ id: string; title: string; calendar: string; start: string; end: string; all_day: boolean; location?: string }>;
  alerts: Array<{
    id: string;
    day: string;
    status: string;
    level: string;
    title: string;
    message: string;
    reason: string;
    sentAt: string | null;
  }>;
  memories: Array<{ id: number; kind: string; title: string; content: string }>;
  notes: Array<{ id: number; title: string; body: string }>;
  conversations: { imessage: ExchangeLine[]; hub: ExchangeLine[] };
  spend: { spentUsd: number; budgetUsd: number; requests: number; deeperModelRequests: number; summary: string };
  waitingForApproval: Array<{ taskId: string; summary: string; createdAt: string }>;
};

// The panel reads Apple's Reminders and Calendar; a reply may search the web.
const PANEL_TIMEOUT_MS = 20_000;
const REPLY_TIMEOUT_MS = 120_000;

export type BrainReply = { reply: string | null; conversation: ExchangeLine[] };

export async function getBrainPanel(): Promise<BrainPanel> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<BrainPanel>(["api", "brain", "panel", "--json"]);
  }
  return requestAriApi<BrainPanel>("GET", "/brain/panel", { timeoutMs: PANEL_TIMEOUT_MS });
}

export async function sendToAri(text: string): Promise<BrainReply> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<BrainReply>(["api", "brain", "message", "--text", text, "--json"]);
  }
  return requestAriApi<BrainReply>("POST", "/brain/messages", { body: { text }, timeoutMs: REPLY_TIMEOUT_MS });
}

export type ContentScript = { hook: string; beats: string[]; caption: string; by?: string };

export type ScriptReview = {
  passed: boolean;
  truth: string[];
  rules: string[];
  notes: string[];
  hookScore?: number;
  flowScore?: number;
  reviewedAt: string;
};

export type ContentItem = {
  id: string;
  kind: string;
  title: string;
  hook: string;
  status: string;
  dayNumber: number | null;
  date: string | null;
  lessons: string[];
  story: string;
  scripts: ContentScript[];
  format: string;
  // The finished video, once ARI's studio made it.
  video: { path: string; voice: string; producedAt: string } | null;
  // ARI's last review of the scripts, and whether it read the current version.
  review: ScriptReview | null;
  reviewCurrent: boolean;
  producing?: boolean;
  updatedAt: string;
  postedAt: string | null;
};

export type ContentLibrary = {
  items: ContentItem[];
  counts: Record<string, number>;
  statuses: string[];
  // Where an item can go from each stage, as ARI allows it.
  moves: Record<string, string[]>;
};

// ARI's content library: every building day, with its stage in the content process.
export async function getContentLibrary(): Promise<ContentLibrary> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<ContentLibrary>(["api", "content", "list", "--json"]);
  }
  return requestAriApi<ContentLibrary>("GET", "/content", { timeoutMs: PANEL_TIMEOUT_MS });
}

export async function setContentStatus(itemId: string, status: string): Promise<ContentItem> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<ContentItem>(["api", "content", "status", "--id", itemId, "--status", status, "--json"]);
  }
  return requestAriApi<ContentItem>("POST", `/content/${encodeURIComponent(itemId)}/status`, {
    body: { status },
    timeoutMs: PANEL_TIMEOUT_MS,
  });
}

export async function editContentScript(itemId: string, number: number, script: ContentScript): Promise<ContentItem> {
  if (isSubprocessBridgeMode()) {
    const beats = script.beats.flatMap((beat) => ["--beat", beat]);
    return runCanonicalJsonCommand<ContentItem>([
      "api", "content", "edit", "--id", itemId, "--script", String(number), "--hook", script.hook, ...beats,
      "--caption", script.caption, "--json",
    ]);
  }
  return requestAriApi<ContentItem>("PUT", `/content/${encodeURIComponent(itemId)}/scripts/${number}`, {
    body: { hook: script.hook, beats: script.beats, caption: script.caption },
    timeoutMs: PANEL_TIMEOUT_MS,
  });
}

// ARI's editor reads the script against that day's commits; it takes a model call.
export async function reviewContent(itemId: string): Promise<ContentItem> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<ContentItem>(["api", "content", "review", "--id", itemId, "--json"]);
  }
  return requestAriApi<ContentItem>("POST", `/content/${encodeURIComponent(itemId)}/review`, { timeoutMs: REPLY_TIMEOUT_MS });
}

// What ARI said went wrong, in its own words when it gave some.
export function ariErrorMessage(error: unknown, fallback = "ARI didn't answer."): string {
  if (error instanceof AriApiError) {
    const detail = (error.details as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return error instanceof Error ? error.message : fallback;
}
