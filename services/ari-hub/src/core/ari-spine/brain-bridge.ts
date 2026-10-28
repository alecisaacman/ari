import { isSubprocessBridgeMode, requestAriApi, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

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
  builds?: Array<{ id: string; title: string; why: string; brief: string; skill_id: string | null; status: string; proposed_at: string }>;
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

export type BrainReply = { reply: string | null; conversation: ExchangeLine[] };

export async function getBrainPanel(): Promise<BrainPanel> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<BrainPanel>(["api", "brain", "panel", "--json"]);
  }
  return requestAriApi<BrainPanel>("GET", "/brain/panel");
}

export async function sendToAri(text: string): Promise<BrainReply> {
  if (isSubprocessBridgeMode()) {
    return runCanonicalJsonCommand<BrainReply>(["api", "brain", "message", "--text", text, "--json"]);
  }
  return requestAriApi<BrainReply>("POST", "/brain/messages", { body: { text } });
}
