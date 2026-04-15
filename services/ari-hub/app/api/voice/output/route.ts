import { NextResponse } from "next/server";

import { handleVoiceOutputRequest } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => null)) as { text?: string } | null;
    const text = body?.text || "";
    const payload = await handleVoiceOutputRequest(text);

    if ("useBrowserTts" in payload) {
      return NextResponse.json(payload);
    }

    return new Response(payload.audioBuffer, {
      status: 200,
      headers: {
        "Content-Type": payload.contentType,
        "Cache-Control": "no-store"
      }
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to generate speech output." },
      { status: 400 }
    );
  }
}
