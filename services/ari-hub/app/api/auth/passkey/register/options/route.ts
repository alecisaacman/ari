import { NextResponse, type NextRequest } from "next/server";

import { getUiSession } from "@/src/core/auth/guard";
import { hasPasskeys, registrationOptions, relyingPartyFor } from "@/src/core/auth/passkeys";

export const runtime = "nodejs";

// The first passkey can be set up from a signed-in session; after that, only the creator adds more.
export async function POST(request: NextRequest) {
  const session = await getUiSession(request);
  if (!session || (hasPasskeys() && session.role !== "creator")) {
    return NextResponse.json({ error: "Only the creator can add a passkey." }, { status: 403 });
  }
  return NextResponse.json(await registrationOptions(relyingPartyFor(request), session.sid));
}
