import { NextResponse, type NextRequest } from "next/server";

import { hasValidTriggerToken } from "@/src/core/auth/guard";
import { handleTriggerRequest } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!hasValidTriggerToken(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const payload = await handleTriggerRequest(body);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to process trigger request." },
      { status: 400 }
    );
  }
}
