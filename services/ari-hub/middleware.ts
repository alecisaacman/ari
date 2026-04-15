import { NextResponse, type NextRequest } from "next/server";

import { verifySessionToken } from "@/src/core/auth/session";

const ALLOWED_PATHS = new Set([
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/trigger",
  "/api/health"
]);

function isPublicPath(pathname: string): boolean {
  if (ALLOWED_PATHS.has(pathname)) {
    return true;
  }

  return pathname.startsWith("/_next/") || pathname === "/favicon.ico";
}

export async function middleware(request: NextRequest) {
  if (isPublicPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const sessionCookieName = "ari_session";
  const authSecret = process.env.ARI_AUTH_SECRET || "replace-with-a-long-random-secret";
  const sessionToken = request.cookies.get(sessionCookieName)?.value;
  const isAuthorized = Boolean(await verifySessionToken(sessionToken, authSecret));

  if (isAuthorized) {
    return NextResponse.next();
  }

  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = new URL("/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"]
};
