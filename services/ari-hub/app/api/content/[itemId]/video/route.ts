import { createReadStream, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";

import { NextResponse, type NextRequest } from "next/server";

import { getContentLibrary } from "@/src/core/ari-spine/brain-bridge";
import { getUiSession } from "@/src/core/auth/guard";

export const runtime = "nodejs";

// Only videos ARI's studio made are served: files under ~/ARI/media/out.
const STUDIO_OUT = path.join(process.env.ARI_HOME || path.join(homedir(), "ARI"), "media", "out");

// A content item's finished video, for watching on the Content page. Serves byte ranges,
// which Safari needs to play and seek video.
export async function GET(request: NextRequest, context: { params: Promise<{ itemId: string }> }) {
  const session = await getUiSession(request);
  if (!session || session.role !== "creator") {
    return NextResponse.json({ error: "Only the creator can watch content." }, { status: 403 });
  }
  const { itemId } = await context.params;
  const library = await getContentLibrary();
  const file = library.items.find((item) => item.id === itemId)?.video?.path;
  const resolved = file ? path.resolve(file) : null;
  if (!resolved || !resolved.startsWith(STUDIO_OUT + path.sep)) {
    return NextResponse.json({ error: "No video for that item yet." }, { status: 404 });
  }
  let size: number;
  try {
    size = statSync(resolved).size;
  } catch {
    return NextResponse.json({ error: "The video file is missing." }, { status: 404 });
  }
  const range = /bytes=(\d*)-(\d*)/.exec(request.headers.get("range") || "");
  const start = range && range[1] ? Number(range[1]) : 0;
  const end = range && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
  const body = Readable.toWeb(createReadStream(resolved, { start, end })) as ReadableStream;
  return new NextResponse(body, {
    status: range ? 206 : 200,
    headers: {
      "Content-Type": "video/mp4",
      "Content-Length": String(end - start + 1),
      "Accept-Ranges": "bytes",
      ...(range ? { "Content-Range": `bytes ${start}-${end}/${size}` } : {}),
      "Cache-Control": "private, no-store",
    },
  });
}
