import { NextResponse } from "next/server";

import { createAuthSession } from "@/src/core/auth/repository";
import { getConfig } from "@/src/core/config";
import { createSessionToken } from "@/src/core/auth/session";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { password?: string } | null;
  const config = getConfig();

  if (!body?.password || body.password !== config.uiPassword) {
    return NextResponse.json({ error: "Invalid password." }, { status: 401 });
  }

  const expiresAtEpochSeconds = Math.floor(Date.now() / 1000) + config.sessionTtlSeconds;
  const authSession = createAuthSession({
    deviceLabel: request.headers.get("x-ari-device-name") || undefined,
    userAgent: request.headers.get("user-agent") || undefined,
    expiresAtEpochSeconds
  });
  const sessionToken = await createSessionToken(config.authSecret, config.sessionTtlSeconds, authSession.id);
  const response = NextResponse.json({ ok: true, sessionId: authSession.id });
  response.cookies.set(config.sessionCookieName, sessionToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: config.sessionTtlSeconds
  });
  return response;
}
