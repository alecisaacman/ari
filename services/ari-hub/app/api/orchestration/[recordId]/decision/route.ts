import { NextResponse } from "next/server";

import { handleAlecDecision } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ recordId: string }> }) {
  try {
    const { recordId } = await context.params;
    const body = (await request.json().catch(() => null)) as { decision?: string } | null;
    const payload = await handleAlecDecision(recordId, body?.decision || "");
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to record Alec decision." },
      { status: 400 }
    );
  }
}
