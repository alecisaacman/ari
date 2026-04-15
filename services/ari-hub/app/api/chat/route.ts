import { NextResponse } from "next/server";

import { handleChatRequest } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const payload = await handleChatRequest(body);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to process chat request." },
      { status: 400 }
    );
  }
}
