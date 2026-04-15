import { deriveCanonicalAwareness, getLatestCanonicalAwareness, storeCanonicalAwareness } from "@/src/core/ari-spine/policy-bridge";
import { getDatabase } from "@/src/core/db/database";
import type { ActiveStateSnapshot, AwarenessSnapshot, DecisionRecord } from "@/src/core/memory/types";

type AwarenessStateInput = Omit<ActiveStateSnapshot, "awareness">;

function compactText(value: string, max = 88): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, max - 3)}...`;
}

function pickRecentIntent(limit = 3): string[] {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT content
       FROM messages
       WHERE role = 'user'
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit * 3) as Array<{ content: string }>;

  const unique = new Set<string>();
  const intents: string[] = [];
  for (const row of rows) {
    const text = compactText(row.content, 88);
    const key = text.toLowerCase();
    if (!text || unique.has(key)) {
      continue;
    }
    unique.add(key);
    intents.push(text);
    if (intents.length >= limit) {
      break;
    }
  }

  return intents;
}

function normalizeRecentDecisions(decisions: DecisionRecord[]): DecisionRecord[] {
  return decisions.slice(0, 4).map((decision) => ({
    id: decision.id,
    title: decision.title,
    body: decision.body,
    source: decision.source,
    createdAt: decision.createdAt
  }));
}

function isStaticBuildPhase(): boolean {
  const phase = process.env.NEXT_PHASE || "";
  return phase.includes("phase-production-build");
}

export function buildAwarenessSnapshot(input: AwarenessStateInput): AwarenessSnapshot {
  return deriveCanonicalAwareness({
    pendingApprovals: input.pendingApprovals,
    recentIntent: pickRecentIntent(3),
    recentDecisions: normalizeRecentDecisions(input.recentDecisions)
  });
}

export function getLatestAwarenessSnapshot(): AwarenessSnapshot | null {
  return getLatestCanonicalAwareness();
}

export function storeAwarenessSnapshot(snapshot: AwarenessSnapshot): { snapshot: AwarenessSnapshot; changed: boolean } {
  if (isStaticBuildPhase()) {
    return { snapshot, changed: false };
  }
  try {
    return storeCanonicalAwareness(snapshot);
  } catch {
    return { snapshot, changed: false };
  }
}
