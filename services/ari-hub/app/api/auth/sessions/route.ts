import { NextResponse } from "next/server";

import { getConfig } from "@/src/core/config";
import { decodeSessionToken, readCookieValue } from "@/src/core/auth/session";
import { getActiveSessions, requireCurrentSessionId } from "@/src/core/auth/session-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const config = getConfig();
    const sessionCookie = readCookieValue(request.headers.get("cookie"), config.sessionCookieName);
    const payload = await decodeSessionToken(sessionCookie, config.authSecret);
    const currentSessionId = requireCurrentSessionId(payload);

    return NextResponse.json({
      currentSessionId,
      sessions: getActiveSessions(currentSessionId)
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to load sessions." },
      { status: 401 }
    );
  }
}
