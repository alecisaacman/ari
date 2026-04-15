import { NextResponse } from "next/server";

import { handleOrchestrationDispatch } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(_request: Request, context: { params: Promise<{ recordId: string }> }) {
  try {
    const { recordId } = await context.params;
    const payload = await handleOrchestrationDispatch(recordId);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to dispatch the builder instruction." },
      { status: 400 }
    );
  }
}
