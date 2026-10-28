"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import type { ExchangeLine } from "@/src/core/ari-spine/brain-bridge";

import { THINKING_EVENT } from "./pet";

// Talk to ARI from the hub, laid out like Messages: you on the right, ARI on the left.
// The message goes to ARI's one brain, the same one iMessage reaches.
export function HubChat({ initial }: { initial: ExchangeLine[] }) {
  const [lines, setLines] = useState<ExchangeLine[]>(initial);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines, sending]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent(THINKING_EVENT, { detail: sending }));
  }, [sending]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) {
      return;
    }
    setSending(true);
    setError(null);
    setLines((current) => [...current, { role: "alec", text: message }]);
    setDraft("");
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "ARI didn't answer.");
      }
      setLines(payload.conversation);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ARI didn't answer.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="hub-chat">
      <div className="hub-chat-scroll" aria-live="polite">
        {lines.length === 0 ? <p className="hub-quiet">Say anything. ARI is listening.</p> : null}
        {lines.map((line, index) => (
          <div key={index} className={`hub-bubble hub-bubble-${line.role === "alec" ? "me" : "ari"}`}>
            {line.text}
          </div>
        ))}
        {sending ? (
          <div className="hub-bubble hub-bubble-ari hub-typing" aria-label="ARI is thinking">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        <div ref={end} />
      </div>
      {error ? <p className="hub-error">{error}</p> : null}
      <form onSubmit={send} className="hub-compose">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Message ARI"
          aria-label="Message ARI"
        />
        <button type="submit" disabled={sending || !draft.trim()} aria-label="Send">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </div>
  );
}
