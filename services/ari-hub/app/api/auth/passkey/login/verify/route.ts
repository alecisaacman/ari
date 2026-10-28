import { NextResponse } from "next/server";
import type { AuthenticationResponseJSON } from "@simplewebauthn/server";

import { issueSession } from "@/src/core/auth/issue";
import { relyingPartyFor, verifyPasskeyLogin } from "@/src/core/auth/passkeys";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const response = (await request.json().catch(() => null)) as AuthenticationResponseJSON | null;
  if (!response || !(await verifyPasskeyLogin(relyingPartyFor(request), response).catch(() => false))) {
    return NextResponse.json({ error: "Touch ID didn't verify." }, { status: 401 });
  }
  return issueSession(request, "creator");
}
