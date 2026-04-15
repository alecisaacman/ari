import { NextResponse } from "next/server";

import { getActivitySnapshot } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function GET() {
  try {
    const payload = await getActivitySnapshot();
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to load activity." },
      { status: 400 }
    );
  }
}
