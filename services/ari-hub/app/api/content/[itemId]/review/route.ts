import { NextResponse, type NextRequest } from "next/server";

import { ariErrorMessage, reviewContent } from "@/src/core/ari-spine/brain-bridge";
import { getUiSession } from "@/src/core/auth/guard";

export const runtime = "nodejs";

// Ask ARI's editor to review a day's script: pass, or notes to fix.
export async function POST(request: NextRequest, context: { params: Promise<{ itemId: string }> }) {
  const session = await getUiSession(request);
  if (!session || session.role !== "creator") {
    return NextResponse.json({ error: "Only the creator can ask for reviews." }, { status: 403 });
  }
  try {
    const { itemId } = await context.params;
    return NextResponse.json(await reviewContent(itemId));
  } catch (error) {
    return NextResponse.json({ error: ariErrorMessage(error) }, { status: 400 });
  }
}
