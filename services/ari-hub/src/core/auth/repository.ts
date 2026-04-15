import { getDatabase } from "@/src/core/db/database";

export type AuthSessionRecord = {
  id: string;
  userRole: "user";
  deviceLabel: string;
  userAgent: string;
  createdAt: string;
  lastSeenAt: string;
  expiresAt: string;
  revokedAt: string | null;
};

function now(): string {
  return new Date().toISOString();
}

function toIsoFromEpochSeconds(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString();
}

function mapSessionRow(row: {
  id: string;
  user_role: "user";
  device_label: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
}): AuthSessionRecord {
  return {
    id: row.id,
    userRole: row.user_role,
    deviceLabel: row.device_label,
    userAgent: row.user_agent,
    createdAt: row.created_at,
    lastSeenAt: row.last_seen_at,
    expiresAt: row.expires_at,
    revokedAt: row.revoked_at
  };
}

export function createAuthSession(input?: { deviceLabel?: string; userAgent?: string; expiresAtEpochSeconds?: number }): AuthSessionRecord {
  const database = getDatabase();
  const timestamp = now();
  const record: AuthSessionRecord = {
    id: crypto.randomUUID(),
    userRole: "user",
    deviceLabel: input?.deviceLabel?.trim() || "browser",
    userAgent: input?.userAgent?.trim() || "unknown",
    createdAt: timestamp,
    lastSeenAt: timestamp,
    expiresAt: input?.expiresAtEpochSeconds ? toIsoFromEpochSeconds(input.expiresAtEpochSeconds) : toIsoFromEpochSeconds(Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7),
    revokedAt: null
  };

  database
    .prepare(
      `INSERT INTO auth_sessions
       (id, user_role, device_label, user_agent, created_at, last_seen_at, expires_at, revoked_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      record.id,
      record.userRole,
      record.deviceLabel,
      record.userAgent,
      record.createdAt,
      record.lastSeenAt,
      record.expiresAt,
      record.revokedAt
    );

  return record;
}

export function getAuthSession(sessionId: string): AuthSessionRecord | null {
  const database = getDatabase();
  const row = database
    .prepare(
      `SELECT id, user_role, device_label, user_agent, created_at, last_seen_at, expires_at, revoked_at
       FROM auth_sessions
       WHERE id = ?`
    )
    .get(sessionId) as
    | {
        id: string;
        user_role: "user";
        device_label: string;
        user_agent: string;
        created_at: string;
        last_seen_at: string;
        expires_at: string;
        revoked_at: string | null;
      }
    | undefined;

  return row ? mapSessionRow(row) : null;
}

export function listActiveAuthSessions(): AuthSessionRecord[] {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT id, user_role, device_label, user_agent, created_at, last_seen_at, expires_at, revoked_at
       FROM auth_sessions
       WHERE revoked_at IS NULL
       ORDER BY last_seen_at DESC`
    )
    .all() as Array<{
    id: string;
    user_role: "user";
    device_label: string;
    user_agent: string;
    created_at: string;
    last_seen_at: string;
    expires_at: string;
    revoked_at: string | null;
  }>;

  const timestamp = now();
  return rows.map(mapSessionRow).filter((session) => session.expiresAt > timestamp);
}

export function touchAuthSession(sessionId: string): void {
  const database = getDatabase();
  database.prepare("UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?").run(now(), sessionId);
}

export function revokeAuthSession(sessionId: string): void {
  const database = getDatabase();
  database.prepare("UPDATE auth_sessions SET revoked_at = ? WHERE id = ?").run(now(), sessionId);
}

export function isAuthSessionActive(sessionId: string): boolean {
  const session = getAuthSession(sessionId);
  if (!session) {
    return false;
  }

  if (session.revokedAt) {
    return false;
  }

  return session.expiresAt > now();
}
