"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

export function LoginForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    startTransition(async () => {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ password })
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Unable to sign in." }));
        setError(payload.error || "Unable to sign in.");
        return;
      }

      router.push("/");
      router.refresh();
    });
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        autoComplete="username"
        name="username"
        readOnly
        tabIndex={-1}
        type="text"
        value="ari-owner"
        style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }}
      />
      <label>
        <span className="eyebrow">Password</span>
        <input
          autoFocus
          autoComplete="current-password"
          name="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Enter your ARI password"
        />
      </label>
      <div className="login-actions" style={{ marginTop: 18 }}>
        <button className="button button-primary" disabled={pending} type="submit">
          {pending ? "Entering..." : "Open ARI"}
        </button>
      </div>
      {error ? <p className="error-text" style={{ marginTop: 14 }}>{error}</p> : null}
    </form>
  );
}
