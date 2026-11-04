import { NextResponse, type NextRequest } from "next/server";

import { setContentStatus } from "@/src/core/ari-spine/brain-bridge";
import { getUiSession } from "@/src/core/auth/guard";

export const runtime = "nodejs";

// Move a content item along (draft, ready, posted, skipped). Content is the creator's side.
export async function POST(request: NextRequest, context: { params: Promise<{ itemId: string }> }) {
  const session = await getUiSession(request);
  if (!session || session.role !== "creator") {
    return NextResponse.json({ error: "Only the creator can change content." }, { status: 403 });
  }
  try {
    const { itemId } = await context.params;
    const body = (await request.json()) as { status?: unknown };
    if (typeof body.status !== "string") {
      return NextResponse.json({ error: "Say which status." }, { status: 400 });
    }
    return NextResponse.json(await setContentStatus(itemId, body.status));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "ARI didn't answer." }, { status: 502 });
  }
}
