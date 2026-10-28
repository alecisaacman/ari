import { NextResponse } from "next/server";

import { hasPasskeys, loginOptions, relyingPartyFor } from "@/src/core/auth/passkeys";

export const runtime = "nodejs";

export async function POST(request: Request) {
  if (!hasPasskeys()) {
    return NextResponse.json({ error: "Touch ID isn't set up yet." }, { status: 404 });
  }
  return NextResponse.json(await loginOptions(relyingPartyFor(request)));
}
