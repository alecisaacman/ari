import { NextResponse } from "next/server";

import { handleApprovalDecision } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ approvalId: string }> }) {
  try {
    const { approvalId } = await context.params;
    const body = (await request.json().catch(() => null)) as { decision?: "approve" | "deny" } | null;
    if (body?.decision !== "approve" && body?.decision !== "deny") {
      return NextResponse.json({ error: "decision must be approve or deny." }, { status: 400 });
    }

    const payload = await handleApprovalDecision(approvalId, body.decision);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to resolve approval." },
      { status: 400 }
    );
  }
}
