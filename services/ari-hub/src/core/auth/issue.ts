import { NextResponse } from "next/server";

import { createAuthSession } from "@/src/core/auth/repository";
import { createSessionToken, type SessionRole } from "@/src/core/auth/session";
import { getConfig } from "@/src/core/config";

// Start a signed-in session and set its cookie on the response.
export async function issueSession(request: Request, role: SessionRole, body: Record<string, unknown> = {}) {
  const config = getConfig();
  const expiresAtEpochSeconds = Math.floor(Date.now() / 1000) + config.sessionTtlSeconds;
  const authSession = createAuthSession({
    deviceLabel: request.headers.get("x-ari-device-name") || undefined,
    userAgent: request.headers.get("user-agent") || undefined,
    expiresAtEpochSeconds,
    role,
  });
  const token = await createSessionToken(config.authSecret, config.sessionTtlSeconds, authSession.id, role);
  const response = NextResponse.json({ ok: true, role, sessionId: authSession.id, ...body });
  response.cookies.set(config.sessionCookieName, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: config.sessionTtlSeconds,
  });
  return response;
}
