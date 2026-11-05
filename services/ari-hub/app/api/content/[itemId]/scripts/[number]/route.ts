import { NextResponse, type NextRequest } from "next/server";

import { ariErrorMessage, editContentScript } from "@/src/core/ari-spine/brain-bridge";
import { getUiSession } from "@/src/core/auth/guard";

export const runtime = "nodejs";

// Alec's own version of a day's script. It goes back to idea until ARI reviews it again.
export async function PUT(request: NextRequest, context: { params: Promise<{ itemId: string; number: string }> }) {
  const session = await getUiSession(request);
  if (!session || session.role !== "creator") {
    return NextResponse.json({ error: "Only the creator can change content." }, { status: 403 });
  }
  try {
    const { itemId, number } = await context.params;
    const body = (await request.json()) as { hook?: unknown; beats?: unknown; caption?: unknown };
    if (typeof body.hook !== "string" || !Array.isArray(body.beats)) {
      return NextResponse.json({ error: "A script needs a hook and beats." }, { status: 400 });
    }
    const beats = body.beats.filter((beat): beat is string => typeof beat === "string");
    const caption = typeof body.caption === "string" ? body.caption : "";
    return NextResponse.json(await editContentScript(itemId, Number(number), { hook: body.hook, beats, caption }));
  } catch (error) {
    return NextResponse.json({ error: ariErrorMessage(error) }, { status: 400 });
  }
}
