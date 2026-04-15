const SESSION_VERSION = 1;

export type SessionPayload = {
  v: number;
  role: "user";
  sid: string;
  iat: number;
  exp: number;
};

function toBase64Url(value: Uint8Array | string): string {
  const buffer = typeof value === "string" ? Buffer.from(value, "utf8") : Buffer.from(value);
  return buffer.toString("base64url");
}

function fromBase64Url(value: string): Uint8Array {
  return Uint8Array.from(Buffer.from(value, "base64url"));
}

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await importHmacKey(secret);
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return toBase64Url(new Uint8Array(signature));
}

export async function createSessionToken(secret: string, ttlSeconds: number, sessionId?: string): Promise<string> {
  const issuedAt = Math.floor(Date.now() / 1000);
  const payload: SessionPayload = {
    v: SESSION_VERSION,
    role: "user",
    sid: sessionId || crypto.randomUUID(),
    iat: issuedAt,
    exp: issuedAt + ttlSeconds
  };
  const encodedPayload = toBase64Url(JSON.stringify(payload));
  const encodedSignature = await signPayload(encodedPayload, secret);
  return `${encodedPayload}.${encodedSignature}`;
}

export async function decodeSessionToken(token: string | undefined, secret: string): Promise<SessionPayload | null> {
  if (!token) {
    return null;
  }

  const [payloadPart, signaturePart] = token.split(".");
  if (!payloadPart || !signaturePart) {
    return null;
  }

  const expectedSignature = await signPayload(payloadPart, secret);
  if (expectedSignature !== signaturePart) {
    return null;
  }

  try {
    const payloadJson = new TextDecoder().decode(fromBase64Url(payloadPart));
    const payload = JSON.parse(payloadJson) as SessionPayload;
    if (
      payload.v !== SESSION_VERSION ||
      payload.role !== "user" ||
      typeof payload.sid !== "string" ||
      typeof payload.iat !== "number" ||
      payload.exp < Math.floor(Date.now() / 1000)
    ) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

export async function verifySessionToken(token: string | undefined, secret: string): Promise<SessionPayload | null> {
  return decodeSessionToken(token, secret);
}

export function readBearerToken(headerValue: string | null): string | null {
  if (!headerValue) {
    return null;
  }

  const match = headerValue.match(/^Bearer\s+(.+)$/i);
  return match ? match[1] : null;
}

export function readCookieValue(cookieHeader: string | null, cookieName: string): string | undefined {
  if (!cookieHeader) {
    return undefined;
  }

  return cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${cookieName}=`))
    ?.slice(cookieName.length + 1);
}
