import { NextResponse } from "next/server";

import { getHealthSnapshot } from "@/src/core/api/services";

export const runtime = "nodejs";

export async function GET() {
  const payload = await getHealthSnapshot();
  return NextResponse.json(payload);
}
