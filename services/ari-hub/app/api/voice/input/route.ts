import { NextResponse } from "next/server";

import { handleVoiceInputRequest } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const payload = await handleVoiceInputRequest(formData);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to process voice input." },
      { status: 400 }
    );
  }
}
