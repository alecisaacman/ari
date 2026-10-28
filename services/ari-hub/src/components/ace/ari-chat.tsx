"use client";

import { useState, type FormEvent } from "react";

import type { ExchangeLine } from "@/src/core/ari-spine/brain-bridge";

// Talk to ARI from the hub. The message goes to ARI's one brain, the same one
// iMessage reaches; the hub only carries it.
export function AriChat({ initial }: { initial: ExchangeLine[] }) {
  const [lines, setLines] = useState<ExchangeLine[]>(initial);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        body: JSON.stringify({ message })
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
    <div className="ace-ari-chat">
      <ul className="ace-ari-transcript" aria-live="polite">
        {lines.map((line, index) => (
          <li key={index} className={`ace-ari-line ace-ari-line-${line.role}`}>
            <span>{line.role === "alec" ? "You" : "ARI"}</span> {line.text}
          </li>
        ))}
        {sending ? <li className="ace-ari-line ace-ari-line-ari">ARI is thinking...</li> : null}
      </ul>
      {error ? <p className="ace-readonly-warning">{error}</p> : null}
      <form onSubmit={send} className="ace-ari-compose">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Say something to ARI"
          aria-label="Message ARI"
        />
        <button type="submit" disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
