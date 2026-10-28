import { NextResponse } from "next/server";

import { issueSession } from "@/src/core/auth/issue";
import { getConfig } from "@/src/core/config";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { password?: string } | null;
  const config = getConfig();

  if (!body?.password || body.password !== config.uiPassword) {
    return NextResponse.json({ error: "Invalid password." }, { status: 401 });
  }

  // The password opens the Today side; Touch ID opens the rest.
  return issueSession(request, "user");
}
