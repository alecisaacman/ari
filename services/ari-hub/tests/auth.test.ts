import assert from "node:assert/strict";
import test from "node:test";

import { createAuthSession, isAuthSessionActive, revokeAuthSession } from "../src/core/auth/repository";
import { getActiveSessions, revokeOtherSession } from "../src/core/auth/session-service";
import { createSessionToken, readBearerToken, verifySessionToken } from "../src/core/auth/session";
import { setupIsolatedRuntime, teardownIsolatedRuntime } from "./helpers";

test("session tokens verify correctly", async () => {
  const token = await createSessionToken("secret", 60, "session-a");
  const payload = await verifySessionToken(token, "secret");
  assert.ok(payload);
  assert.equal(payload?.role, "user");
  assert.equal(payload?.sid, "session-a");
});

test("session tokens reject invalid signature", async () => {
  const token = await createSessionToken("secret", 60, "session-a");
  const payload = await verifySessionToken(token, "other-secret");
  assert.equal(payload, null);
});

test("each login session gets a unique token and can be revoked independently", async () => {
  setupIsolatedRuntime("auth");
  try {
    const sessionOne = createAuthSession({ deviceLabel: "desktop", userAgent: "Desktop Browser", expiresAtEpochSeconds: Math.floor(Date.now() / 1000) + 60 });
    const sessionTwo = createAuthSession({ deviceLabel: "phone", userAgent: "Phone Browser", expiresAtEpochSeconds: Math.floor(Date.now() / 1000) + 60 });

    const tokenOne = await createSessionToken("secret", 60, sessionOne.id);
    const tokenTwo = await createSessionToken("secret", 60, sessionTwo.id);
    const payloadOne = await verifySessionToken(tokenOne, "secret");
    const payloadTwo = await verifySessionToken(tokenTwo, "secret");

    assert.notEqual(tokenOne, tokenTwo);
    assert.equal(payloadOne?.sid, sessionOne.id);
    assert.equal(payloadTwo?.sid, sessionTwo.id);
    assert.equal(isAuthSessionActive(sessionOne.id), true);
    assert.equal(isAuthSessionActive(sessionTwo.id), true);

    revokeAuthSession(sessionOne.id);

    assert.equal(isAuthSessionActive(sessionOne.id), false);
    assert.equal(isAuthSessionActive(sessionTwo.id), true);
  } finally {
    teardownIsolatedRuntime();
  }
});

test("bearer tokens are parsed from authorization header", () => {
  assert.equal(readBearerToken("Bearer abc123"), "abc123");
  assert.equal(readBearerToken("Basic abc123"), null);
  assert.equal(readBearerToken(null), null);
});

test("active session list marks current session and only revokes other sessions", () => {
  setupIsolatedRuntime("session-list");
  try {
    const current = createAuthSession({ deviceLabel: "desktop", userAgent: "Desktop Browser", expiresAtEpochSeconds: Math.floor(Date.now() / 1000) + 60 });
    const other = createAuthSession({ deviceLabel: "phone", userAgent: "Phone Browser", expiresAtEpochSeconds: Math.floor(Date.now() / 1000) + 60 });

    const sessions = getActiveSessions(current.id);
    assert.equal(sessions.length, 2);
    assert.equal(sessions.find((session) => session.id === current.id)?.current, true);
    assert.equal(sessions.find((session) => session.id === other.id)?.current, false);

    assert.throws(() => revokeOtherSession(current.id, current.id), /Current session/);
    revokeOtherSession(other.id, current.id);
    assert.equal(isAuthSessionActive(other.id), false);
    assert.equal(isAuthSessionActive(current.id), true);
  } finally {
    teardownIsolatedRuntime();
  }
});
