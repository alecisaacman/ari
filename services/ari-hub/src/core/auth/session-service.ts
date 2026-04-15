import { getAuthSession, listActiveAuthSessions, revokeAuthSession } from "@/src/core/auth/repository";
import { type SessionPayload } from "@/src/core/auth/session";
import type { ActiveSessionItem } from "@/src/core/api/types";

function summarizeSessionLabel(deviceLabel: string, userAgent: string): string {
  if (deviceLabel && deviceLabel !== "browser") {
    return deviceLabel;
  }

  if (!userAgent || userAgent === "unknown") {
    return "browser";
  }

  if (/iphone|ios/i.test(userAgent)) {
    return "iPhone browser";
  }

  if (/ipad/i.test(userAgent)) {
    return "iPad browser";
  }

  if (/android/i.test(userAgent)) {
    return "Android browser";
  }

  if (/safari/i.test(userAgent) && !/chrome/i.test(userAgent)) {
    return "Safari";
  }

  if (/chrome/i.test(userAgent)) {
    return "Chrome";
  }

  if (/firefox/i.test(userAgent)) {
    return "Firefox";
  }

  return "browser";
}

export function getActiveSessions(currentSessionId: string): ActiveSessionItem[] {
  return listActiveAuthSessions().map((session) => ({
    id: session.id,
    label: summarizeSessionLabel(session.deviceLabel, session.userAgent),
    userAgent: session.userAgent,
    current: session.id === currentSessionId,
    createdAt: session.createdAt,
    lastSeenAt: session.lastSeenAt
  }));
}

export function revokeOtherSession(targetSessionId: string, currentSessionId: string): void {
  if (targetSessionId === currentSessionId) {
    throw new Error("Current session cannot be revoked from this panel.");
  }

  const session = getAuthSession(targetSessionId);
  if (!session || session.revokedAt || session.expiresAt <= new Date().toISOString()) {
    throw new Error("Session not found.");
  }

  revokeAuthSession(targetSessionId);
}

export function requireCurrentSessionId(payload: SessionPayload | null): string {
  if (!payload?.sid) {
    throw new Error("Active session is required.");
  }

  return payload.sid;
}
