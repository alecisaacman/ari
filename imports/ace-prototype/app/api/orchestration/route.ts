import { NextResponse } from "next/server";

import { getOrchestrationSnapshot, handleBuilderOutputIngest } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function GET() {
  try {
    const payload = await getOrchestrationSnapshot();
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to load orchestration state." },
      { status: 400 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => null)) as { rawOutput?: string; source?: string } | null;
    const payload = await handleBuilderOutputIngest(body?.rawOutput || "", body?.source || "codex");
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to ingest builder output." },
      { status: 400 }
    );
  }
}
