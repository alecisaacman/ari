"use client";

import { useMemo, useState } from "react";

import type { ContentItem, ContentLibrary } from "@/src/core/ari-spine/brain-bridge";

// The content process, in order. Skipped sits outside it.
const PIPELINE = ["idea", "script", "production", "ready", "posted"] as const;

const STAGE: Record<string, { label: string; hint: string }> = {
  idea: { label: "Idea", hint: "ARI wrote it from the day's commits. Check the hook against what really happened." },
  script: { label: "Script", hint: "Approved. The script is set and waiting to be made." },
  production: { label: "Production", hint: "Being recorded, voiced, and edited." },
  ready: { label: "Ready to post", hint: "The finished video exists and can go out." },
  posted: { label: "Posted", hint: "Out in the world." },
  skipped: { label: "Skipped", hint: "Set aside. Bring one back any time." },
};

// What a move is called depends on where the item is now.
function moveLabel(from: string, to: string): string {
  if (to === "skipped") return "Skip";
  if (from === "skipped") return "Bring back";
  if (to === "script") return from === "idea" ? "Approve script" : "Back to script";
  if (to === "production") return from === "script" ? "Start production" : "Back to production";
  if (to === "ready") return "Finished, ready to post";
  if (to === "posted") return "Mark posted";
  if (to === "idea") return "Back to idea";
  return from === "posted" ? "Not posted after all" : STAGE[to]?.label ?? to;
}

type Filter = (typeof PIPELINE)[number] | "skipped" | "all";

// Content: every piece of content and where it is in the content process.
export function Content({ library }: { library: ContentLibrary }) {
  const [items, setItems] = useState<ContentItem[]>(library.items);
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    for (const item of items) {
      result[item.status] = (result[item.status] ?? 0) + 1;
    }
    return result;
  }, [items]);
  const shown = filter === "all" ? items.filter((item) => item.status !== "skipped") : items.filter((item) => item.status === filter);

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
        <p className="content-kicker">Content</p>
        <h1>Day N of building ARI</h1>
        <p>
          Short-form, one video per building day. Each goes idea, script, production, then ready to post, so nothing is ready
          until the finished video exists.
        </p>
      </header>

      <nav className="content-pipeline" aria-label="Stages">
        <button type="button" className={filter === "all" ? "is-on" : ""} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
          <span className="content-stage-name">All</span>
          <span className="content-stage-count">{items.length - (counts.skipped ?? 0)}</span>
        </button>
        {PIPELINE.map((stage) => (
          <button
            key={stage}
            type="button"
            className={filter === stage ? "is-on" : ""}
            aria-pressed={filter === stage}
            onClick={() => setFilter(stage)}
          >
            <span className="content-stage-name">{STAGE[stage].label}</span>
            <span className="content-stage-count">{counts[stage] ?? 0}</span>
          </button>
        ))}
        <button
          type="button"
          className={`content-stage-aside ${filter === "skipped" ? "is-on" : ""}`}
          aria-pressed={filter === "skipped"}
          onClick={() => setFilter("skipped")}
        >
          <span className="content-stage-name">Skipped</span>
          <span className="content-stage-count">{counts.skipped ?? 0}</span>
        </button>
      </nav>
      {filter !== "all" ? <p className="hub-quiet">{STAGE[filter].hint}</p> : null}

      {error ? <p className="chat-error">{error}</p> : null}

      {shown.length ? (
        <ol className="content-list">
          {shown.map((item) => (
            <li key={item.id}>
              <ContentCard
                item={item}
                moves={library.moves[item.status] ?? []}
                busy={busy === item.id}
                onMove={(to) => move(item, to)}
              />
            </li>
          ))}
        </ol>
      ) : (
        <p className="hub-quiet content-empty">Nothing at {filter === "all" ? "any stage" : STAGE[filter].label.toLowerCase()} right now.</p>
      )}
    </div>
  );
}

function ContentCard({
  item,
  moves,
  busy,
  onMove,
}: {
  item: ContentItem;
  moves: string[];
  busy: boolean;
  onMove: (to: string) => void;
}) {
  const step = PIPELINE.indexOf(item.status as (typeof PIPELINE)[number]);
  return (
    <article className={`content-card is-${item.status}`}>
      <details>
        <summary>
          <span className="content-meta">
            <span className="content-day">Day {item.dayNumber}</span>
            <span className="content-date">{item.date ? shortDate(item.date) : ""}</span>
            <span className="content-format">{item.format}</span>
            <span className={`content-status is-${item.status}`}>{STAGE[item.status]?.label ?? item.status}</span>
          </span>
          <span className="content-hook">{item.hook}</span>
          {step >= 0 ? (
            <span className="content-progress" aria-hidden="true">
              {PIPELINE.map((stage, index) => (
                <span key={stage} className={index <= step ? "is-done" : ""} />
              ))}
            </span>
          ) : null}
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
        {moves.map((to, index) => (
          <button key={to} type="button" className={index === 0 ? "is-primary" : ""} disabled={busy} onClick={() => onMove(to)}>
            {moveLabel(item.status, to)}
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
