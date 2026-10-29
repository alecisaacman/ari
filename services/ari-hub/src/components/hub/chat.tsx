"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import type { ExchangeLine } from "@/src/core/ari-spine/brain-bridge";

// Only the latest exchange shows until Alec asks for more, so Today stays calm.
const RECENT_LINES = 2;

// Talk to ARI from the hub, laid out like Messages: you on the right, ARI on the left.
// The message goes to ARI's one brain, the same one iMessage reaches.
export function HubChat({ initial }: { initial: ExchangeLine[] }) {
  const [lines, setLines] = useState<ExchangeLine[]>(initial);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const thread = useRef<HTMLDivElement>(null);

  // Keep the newest message in view inside the thread, without moving the page.
  useEffect(() => {
    if (thread.current) {
      thread.current.scrollTop = thread.current.scrollHeight;
    }
  }, [lines, sending, expanded]);

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

  const shown = expanded ? lines : lines.slice(-RECENT_LINES);
  const hidden = lines.length - shown.length;

  return (
    <section className="chat" aria-label="Talk to ARI">
      {lines.length || sending ? (
        <div className="chat-thread" aria-live="polite" ref={thread}>
          {hidden > 0 ? (
            <button type="button" className="chat-earlier" onClick={() => setExpanded(true)}>
              Earlier messages
            </button>
          ) : null}
          {shown.map((line, index) => (
            <div key={lines.length - shown.length + index} className={`bubble ${line.role === "alec" ? "bubble-me" : "bubble-ari"}`}>
              {line.text}
            </div>
          ))}
          {sending ? (
            <div className="bubble bubble-ari typing" aria-label="ARI is thinking">
              <span />
              <span />
              <span />
            </div>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="chat-error">{error}</p> : null}
      <form onSubmit={send} className="chat-bar">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask ARI"
          aria-label="Message ARI"
        />
        <button type="submit" disabled={sending || !draft.trim()} aria-label="Send">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </section>
  );
}
