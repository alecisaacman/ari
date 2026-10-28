"use client";

import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { useState } from "react";

async function post(path: string, body?: unknown) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "That didn't work.");
  }
  return payload;
}

// "unlock" signs in with an existing passkey; "setup" makes the first one.
export function TouchIdButton({ mode }: { mode: "unlock" | "setup" }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "unlock") {
        const options = await post("/api/auth/passkey/login/options");
        await post("/api/auth/passkey/login/verify", await startAuthentication({ optionsJSON: options }));
      } else {
        const options = await post("/api/auth/passkey/register/options");
        await post("/api/auth/passkey/register/verify", await startRegistration({ optionsJSON: options }));
      }
      router.push("/?tab=ari");
      router.refresh();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Touch ID didn't work.";
      setError(message.includes("timed out or was not allowed") ? "Touch ID was cancelled." : message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="hub-touchid">
      <button className="hub-touchid-button" onClick={go} disabled={busy} type="button">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M12 11v4m-3.5-5.5a3.5 3.5 0 0 1 7 0V14a7 7 0 0 1-1 3.6M6 9a6 6 0 0 1 12 0v4m-12 0v-1m3 7.5A9 9 0 0 1 8.5 14V9.5M3.5 15V9a8.5 8.5 0 0 1 17 0v3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
        {busy ? "Waiting for Touch ID" : mode === "unlock" ? "Unlock with Touch ID" : "Set up Touch ID"}
      </button>
      {error ? <p className="hub-error">{error}</p> : null}
    </div>
  );
}
