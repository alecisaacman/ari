import { NextResponse } from "next/server";

import { getConfig } from "@/src/core/config";
import { decodeSessionToken, readCookieValue } from "@/src/core/auth/session";
import { requireCurrentSessionId, revokeOtherSession } from "@/src/core/auth/session-service";

export const runtime = "nodejs";

export async function DELETE(request: Request, context: { params: Promise<{ sessionId: string }> }) {
  try {
    const config = getConfig();
    const sessionCookie = readCookieValue(request.headers.get("cookie"), config.sessionCookieName);
    const payload = await decodeSessionToken(sessionCookie, config.authSecret);
    const currentSessionId = requireCurrentSessionId(payload);
    const params = await context.params;

    revokeOtherSession(params.sessionId, currentSessionId);

    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to revoke session." },
      { status: 400 }
    );
  }
}
