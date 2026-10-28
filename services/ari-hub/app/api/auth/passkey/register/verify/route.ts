import { NextResponse, type NextRequest } from "next/server";
import type { RegistrationResponseJSON } from "@simplewebauthn/server";

import { getUiSession } from "@/src/core/auth/guard";
import { issueSession } from "@/src/core/auth/issue";
import { hasPasskeys, registerPasskey, relyingPartyFor } from "@/src/core/auth/passkeys";
import { revokeAuthSession } from "@/src/core/auth/repository";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const session = await getUiSession(request);
  if (!session || (hasPasskeys() && session.role !== "creator")) {
    return NextResponse.json({ error: "Only the creator can add a passkey." }, { status: 403 });
  }
  const response = (await request.json().catch(() => null)) as RegistrationResponseJSON | null;
  const label = request.headers.get("x-ari-device-name") || "Touch ID";
  if (!response || !(await registerPasskey(relyingPartyFor(request), session.sid, response, label))) {
    return NextResponse.json({ error: "Touch ID setup didn't verify. Try again." }, { status: 400 });
  }
  revokeAuthSession(session.sid);
  return issueSession(request, "creator");
}
