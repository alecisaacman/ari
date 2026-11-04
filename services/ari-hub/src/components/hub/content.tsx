"use client";

import { useMemo, useState } from "react";

import type { ContentItem, ContentLibrary } from "@/src/core/ari-spine/brain-bridge";

const FILTERS = ["all", "draft", "ready", "posted", "skipped"] as const;
type Filter = (typeof FILTERS)[number];

const LABEL: Record<string, string> = {
  all: "All",
  idea: "Idea",
  draft: "Draft",
  ready: "Ready",
  posted: "Posted",
  skipped: "Skipped",
};

// The moves that make sense from each status, first one most likely.
const MOVES: Record<string, Array<{ to: string; label: string }>> = {
  idea: [{ to: "draft", label: "Start a draft" }, { to: "skipped", label: "Skip" }],
  draft: [{ to: "ready", label: "Mark ready" }, { to: "skipped", label: "Skip" }],
  ready: [{ to: "posted", label: "Mark posted" }, { to: "draft", label: "Back to draft" }],
  posted: [{ to: "ready", label: "Not posted after all" }],
  skipped: [{ to: "draft", label: "Bring back" }],
};

// The Content tab: every building day, what stage it's at, and its hooks and scripts.
export function Content({ library }: { library: ContentLibrary }) {
  const [items, setItems] = useState<ContentItem[]>(library.items);
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const counts = useMemo(() => {
    const result: Record<string, number> = { all: items.length };
    for (const item of items) {
      result[item.status] = (result[item.status] ?? 0) + 1;
    }
    return result;
  }, [items]);
  const shown = filter === "all" ? items : items.filter((item) => item.status === filter);

  async function move(item: ContentItem, to: string) {
    setBusy(item.id);
    setError(null);
    try {
      const response = await fetch(`/api/content/${encodeURIComponent(item.id)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: to }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "ARI didn't save that.");
      }
      setItems((current) => current.map((entry) => (entry.id === item.id ? (payload as ContentItem) : entry)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ARI didn't save that.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="content">
      <header className="content-head">
        <h1>Day N of building ARI</h1>
        <p>
          {items.length} building days. ARI writes each one from that day&apos;s commits as a draft. Check the hook against what really
          happened, then mark it ready.
        </p>
      </header>

      <nav className="content-filters" aria-label="Show">
        {FILTERS.map((name) => (
          <button
            key={name}
            type="button"
            className={filter === name ? "is-on" : ""}
            aria-pressed={filter === name}
            onClick={() => setFilter(name)}
          >
            {LABEL[name]}
            <span>{counts[name] ?? 0}</span>
          </button>
        ))}
      </nav>

      {error ? <p className="chat-error">{error}</p> : null}

      {shown.length ? (
        <ol className="content-list">
          {shown.map((item) => (
            <li key={item.id}>
              <ContentCard item={item} busy={busy === item.id} onMove={(to) => move(item, to)} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="hub-quiet content-empty">Nothing is {LABEL[filter].toLowerCase()} right now.</p>
      )}
    </div>
  );
}

function ContentCard({ item, busy, onMove }: { item: ContentItem; busy: boolean; onMove: (to: string) => void }) {
  return (
    <article className={`content-card is-${item.status}`}>
      <details>
        <summary>
          <span className="content-meta">
            <span className="content-day">Day {item.dayNumber}</span>
            <span className="content-date">{item.date ? shortDate(item.date) : ""}</span>
            <span className={`content-status is-${item.status}`}>{LABEL[item.status] ?? item.status}</span>
          </span>
          <span className="content-hook">{item.hook}</span>
        </summary>

        <div className="content-body">
          {item.scripts.map((script, index) => (
            <section key={index} className="content-script" aria-label={`Video ${index + 1}`}>
              {index > 0 ? <p className="content-alt">{script.hook}</p> : null}
              <ol className="content-beats">
                {script.beats.map((beat, beatIndex) => (
                  <li key={beatIndex}>{beat}</li>
                ))}
              </ol>
              <Caption text={script.caption} />
            </section>
          ))}

          {item.lessons.length ? (
            <section className="content-lessons" aria-label="What ARI learned">
              <h3>What ARI learned</h3>
              <ul>
                {item.lessons.map((lesson, index) => (
                  <li key={index}>{lesson}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-label="The story">
            <h3>The story</h3>
            <p className="content-story">{item.story}</p>
          </section>
        </div>
      </details>

      <div className="content-actions">
        {(MOVES[item.status] ?? []).map((move, index) => (
          <button
            key={move.to}
            type="button"
            className={index === 0 ? "is-primary" : ""}
            disabled={busy}
            onClick={() => onMove(move.to)}
          >
            {move.label}
          </button>
        ))}
        {item.postedAt && item.status === "posted" ? <span className="hub-quiet">Posted {shortDate(item.postedAt)}</span> : null}
      </div>
    </article>
  );
}

function Caption({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  if (!text) {
    return null;
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="content-caption">
      <p>{text}</p>
      <button type="button" onClick={copy}>
        {copied ? "Copied" : "Copy caption"}
      </button>
    </div>
  );
}

function shortDate(value: string): string {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
