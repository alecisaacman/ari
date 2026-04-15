import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { isAuthSessionActive, touchAuthSession } from "@/src/core/auth/repository";
import { getConfig } from "@/src/core/config";
import { readBearerToken, verifySessionToken } from "@/src/core/auth/session";

export async function hasUiSession(request?: NextRequest): Promise<boolean> {
  const config = getConfig();
  const cookieStore = request ? request.cookies : await cookies();
  const session = cookieStore.get(config.sessionCookieName)?.value;
  const payload = await verifySessionToken(session, config.authSecret);
  if (!payload) {
    return false;
  }

  const active = isAuthSessionActive(payload.sid);
  if (active) {
    touchAuthSession(payload.sid);
  }
  return active;
}

export function hasValidTriggerToken(request: NextRequest): boolean {
  const config = getConfig();
  const bearerToken = readBearerToken(request.headers.get("authorization"));
  const headerToken = request.headers.get("x-ari-token");
  return bearerToken === config.triggerToken || headerToken === config.triggerToken;
}
