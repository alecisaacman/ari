import {
  generateAuthenticationOptions,
  generateRegistrationOptions,
  verifyAuthenticationResponse,
  verifyRegistrationResponse,
  type AuthenticationResponseJSON,
  type AuthenticatorTransport,
  type RegistrationResponseJSON,
} from "@simplewebauthn/server";

import { getDatabase } from "@/src/core/db/database";

// Touch ID for the creator. A passkey never leaves Alec's device; ARI keeps only its
// public key. Challenges are single-use and expire after five minutes.

const CHALLENGE_TTL_MS = 5 * 60 * 1000;
const RP_NAME = "ARI";

type PasskeyRow = {
  id: string;
  public_key: string;
  counter: number;
  transports_json: string;
};

export type RelyingParty = { rpID: string; origin: string };

// The passkey belongs to the host the hub was opened on, such as localhost.
export function relyingPartyFor(request: Request): RelyingParty {
  const url = new URL(request.url);
  const host = request.headers.get("host") || url.host;
  const protocol = request.headers.get("x-forwarded-proto") || url.protocol.replace(":", "");
  return { rpID: host.split(":")[0], origin: `${protocol}://${host}` };
}

export function hasPasskeys(): boolean {
  const row = getDatabase().prepare("SELECT COUNT(*) AS count FROM passkeys").get() as { count: number };
  return row.count > 0;
}

function listPasskeys(): PasskeyRow[] {
  return getDatabase().prepare("SELECT id, public_key, counter, transports_json FROM passkeys").all() as PasskeyRow[];
}

function rememberChallenge(challenge: string, purpose: "register" | "login", sessionId: string | null): void {
  const database = getDatabase();
  database.prepare("DELETE FROM passkey_challenges WHERE created_at < ?").run(new Date(Date.now() - CHALLENGE_TTL_MS).toISOString());
  database
    .prepare("INSERT INTO passkey_challenges (challenge, purpose, session_id, created_at) VALUES (?, ?, ?, ?)")
    .run(challenge, purpose, sessionId, new Date().toISOString());
}

function takeChallenge(challenge: string, purpose: "register" | "login", sessionId: string | null): boolean {
  const database = getDatabase();
  const row = database
    .prepare("SELECT purpose, session_id, created_at FROM passkey_challenges WHERE challenge = ?")
    .get(challenge) as { purpose: string; session_id: string | null; created_at: string } | undefined;
  database.prepare("DELETE FROM passkey_challenges WHERE challenge = ?").run(challenge);
  return Boolean(
    row &&
      row.purpose === purpose &&
      row.session_id === sessionId &&
      Date.now() - Date.parse(row.created_at) < CHALLENGE_TTL_MS
  );
}

function clientChallenge(response: { response: { clientDataJSON: string } }): string {
  const clientData = JSON.parse(Buffer.from(response.response.clientDataJSON, "base64url").toString("utf8")) as {
    challenge?: string;
  };
  return clientData.challenge ?? "";
}

export async function registrationOptions(rp: RelyingParty, sessionId: string) {
  const options = await generateRegistrationOptions({
    rpName: RP_NAME,
    rpID: rp.rpID,
    userName: "creator",
    userDisplayName: "ARI creator",
    attestationType: "none",
    excludeCredentials: listPasskeys().map((passkey) => ({ id: passkey.id })),
    authenticatorSelection: { residentKey: "required", userVerification: "required" },
  });
  rememberChallenge(options.challenge, "register", sessionId);
  return options;
}

export async function registerPasskey(
  rp: RelyingParty,
  sessionId: string,
  response: RegistrationResponseJSON,
  label: string
): Promise<boolean> {
  const challenge = clientChallenge(response);
  if (!takeChallenge(challenge, "register", sessionId)) {
    return false;
  }
  const verification = await verifyRegistrationResponse({
    response,
    expectedChallenge: challenge,
    expectedOrigin: rp.origin,
    expectedRPID: rp.rpID,
    requireUserVerification: true,
  });
  if (!verification.verified || !verification.registrationInfo) {
    return false;
  }
  const { credential } = verification.registrationInfo;
  getDatabase()
    .prepare(
      `INSERT INTO passkeys (id, public_key, counter, transports_json, label, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .run(
      credential.id,
      Buffer.from(credential.publicKey).toString("base64url"),
      credential.counter,
      JSON.stringify(credential.transports ?? []),
      label,
      new Date().toISOString()
    );
  return true;
}

export async function loginOptions(rp: RelyingParty) {
  const options = await generateAuthenticationOptions({
    rpID: rp.rpID,
    userVerification: "required",
    allowCredentials: listPasskeys().map((passkey) => ({
      id: passkey.id,
      transports: JSON.parse(passkey.transports_json) as AuthenticatorTransport[],
    })),
  });
  rememberChallenge(options.challenge, "login", null);
  return options;
}

export async function verifyPasskeyLogin(rp: RelyingParty, response: AuthenticationResponseJSON): Promise<boolean> {
  const challenge = clientChallenge(response);
  if (!takeChallenge(challenge, "login", null)) {
    return false;
  }
  const passkey = listPasskeys().find((candidate) => candidate.id === response.id);
  if (!passkey) {
    return false;
  }
  const verification = await verifyAuthenticationResponse({
    response,
    expectedChallenge: challenge,
    expectedOrigin: rp.origin,
    expectedRPID: rp.rpID,
    requireUserVerification: true,
    credential: {
      id: passkey.id,
      publicKey: Uint8Array.from(Buffer.from(passkey.public_key, "base64url")),
      counter: passkey.counter,
      transports: JSON.parse(passkey.transports_json) as AuthenticatorTransport[],
    },
  });
  if (!verification.verified) {
    return false;
  }
  getDatabase()
    .prepare("UPDATE passkeys SET counter = ?, last_used_at = ? WHERE id = ?")
    .run(verification.authenticationInfo.newCounter, new Date().toISOString(), passkey.id);
  return true;
}
