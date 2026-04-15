import { NextResponse } from "next/server";

import { revokeAuthSession } from "@/src/core/auth/repository";
import { getConfig } from "@/src/core/config";
import { decodeSessionToken, readCookieValue } from "@/src/core/auth/session";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const config = getConfig();
  const sessionCookie = readCookieValue(request.headers.get("cookie"), config.sessionCookieName);

  const payload = await decodeSessionToken(sessionCookie, config.authSecret);
  if (payload) {
    revokeAuthSession(payload.sid);
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(config.sessionCookieName, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: 0
  });
  return response;
}
