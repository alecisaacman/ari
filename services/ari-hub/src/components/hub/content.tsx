"use client";

import { useId, useMemo, useState } from "react";

import type { ContentItem, ContentLibrary, ContentScript, ScriptReview } from "@/src/core/ari-spine/brain-bridge";

// The content process, in order. Skipped sits outside it.
const PIPELINE = ["idea", "script", "production", "ready", "posted"] as const;

const STAGE: Record<string, { label: string; hint: string }> = {
  idea: { label: "Idea", hint: "ARI wrote it from the day's commits. Check the hook against what really happened." },
  script: { label: "Script", hint: "Approved. The script is set and waiting to be made." },
  production: { label: "Production", hint: "ARI's studio is voicing and cutting the video. Watch it, then mark it ready." },
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

  // Every change goes through ARI, which answers with the item as it now stands.
  async function call(item: ContentItem, url: string, init: RequestInit): Promise<boolean> {
    setBusy(item.id);
    setError(null);
    try {
      const response = await fetch(url, { ...init, headers: { "Content-Type": "application/json" } });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "ARI didn't save that.");
      }
      setItems((current) => current.map((entry) => (entry.id === item.id ? (payload as ContentItem) : entry)));
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ARI didn't save that.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  const base = (item: ContentItem) => `/api/content/${encodeURIComponent(item.id)}`;
  const move = (item: ContentItem, to: string) => call(item, `${base(item)}/status`, { method: "POST", body: JSON.stringify({ status: to }) });
  const save = (item: ContentItem, number: number, script: ContentScript) =>
    call(item, `${base(item)}/scripts/${number}`, { method: "PUT", body: JSON.stringify(script) });
  const review = (item: ContentItem) => call(item, `${base(item)}/review`, { method: "POST" });

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
                onSave={(number, script) => save(item, number, script)}
                onReview={() => review(item)}
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
  onSave,
  onReview,
}: {
  item: ContentItem;
  moves: string[];
  busy: boolean;
  onMove: (to: string) => void;
  onSave: (number: number, script: ContentScript) => Promise<boolean>;
  onReview: () => Promise<boolean>;
}) {
  const step = PIPELINE.indexOf(item.status as (typeof PIPELINE)[number]);
  const [editing, setEditing] = useState<number | null>(null);
  const editable = item.status === "idea" || item.status === "script";
  const approved = Boolean(item.reviewCurrent && item.review?.passed);
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
          {item.video ? (
            <section className="content-video" aria-label="The video">
              <video controls playsInline preload="metadata" src={`/api/content/${encodeURIComponent(item.id)}/video`} />
              <p className="hub-quiet">
                Made {shortDate(item.video.producedAt)}, narrated by {item.video.voice}.
              </p>
            </section>
          ) : item.status === "production" ? (
            <p className="hub-quiet">ARI&apos;s studio is making this video. It shows up here when it&apos;s done.</p>
          ) : null}
          {item.scripts.map((script, index) =>
            editing === index ? (
              <ScriptEditor
                key={index}
                script={script}
                busy={busy}
                onCancel={() => setEditing(null)}
                onSave={async (changed) => {
                  if (await onSave(index + 1, changed)) {
                    setEditing(null);
                  }
                }}
              />
            ) : (
              <section key={index} className="content-script" aria-label={`Video ${index + 1}`}>
                {index > 0 || script.by === "alec" ? (
                  <p className="content-alt">
                    {script.hook}
                    {script.by === "alec" ? <span className="content-by">Your version</span> : null}
                  </p>
                ) : null}
                <ol className="content-beats">
                  {script.beats.map((beat, beatIndex) => (
                    <li key={beatIndex}>{beat}</li>
                  ))}
                </ol>
                <Caption text={script.caption} />
                {editable ? (
                  <button type="button" className="content-edit" disabled={busy} onClick={() => setEditing(index)}>
                    Edit script
                  </button>
                ) : null}
              </section>
            ),
          )}

          {editable ? <ReviewPanel review={item.review} current={item.reviewCurrent} busy={busy} onReview={onReview} /> : null}

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
        {moves.map((to, index) => {
          // Approving waits for ARI's review to pass the script as it stands.
          const blocked = item.status === "idea" && to === "script" && !approved;
          return (
            <button
              key={to}
              type="button"
              className={index === 0 ? "is-primary" : ""}
              disabled={busy || blocked}
              title={blocked ? "Ask ARI to review the script first" : undefined}
              onClick={() => onMove(to)}
            >
              {moveLabel(item.status, to)}
            </button>
          );
        })}
        {item.status === "idea" && !approved ? <span className="hub-quiet">Open the day and ask ARI to review it first.</span> : null}
        {item.postedAt && item.status === "posted" ? <span className="hub-quiet">Posted {shortDate(item.postedAt)}</span> : null}
      </div>
    </article>
  );
}

function ScriptEditor({
  script,
  busy,
  onSave,
  onCancel,
}: {
  script: ContentScript;
  busy: boolean;
  onSave: (script: ContentScript) => void;
  onCancel: () => void;
}) {
  const [hook, setHook] = useState(script.hook);
  const [beats, setBeats] = useState(script.beats.join("\n"));
  const [caption, setCaption] = useState(script.caption);
  const id = useId();
  const lines = beats.split("\n").map((beat) => beat.trim()).filter(Boolean);
  const seconds = Math.round((hook.split(/\s+/).filter(Boolean).length + lines.join(" ").split(/\s+/).filter(Boolean).length + 9) / 2.5);
  return (
    <form
      className="content-editor"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({ hook, beats: lines, caption });
      }}
    >
      <label htmlFor={`${id}-hook`}>Hook</label>
      <input id={`${id}-hook`} value={hook} onChange={(event) => setHook(event.target.value)} />
      <label htmlFor={`${id}-beats`}>Beats, one per line</label>
      <textarea id={`${id}-beats`} rows={Math.max(4, lines.length + 1)} value={beats} onChange={(event) => setBeats(event.target.value)} />
      <label htmlFor={`${id}-caption`}>Caption</label>
      <textarea id={`${id}-caption`} rows={3} value={caption} onChange={(event) => setCaption(event.target.value)} />
      <p className="hub-quiet">
        {lines.length} beats, about {seconds} seconds spoken. Saving sends it back to idea for ARI to review.
      </p>
      <div className="content-actions">
        <button type="submit" className="is-primary" disabled={busy || !hook.trim() || !lines.length}>
          Save
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ReviewPanel({
  review,
  current,
  busy,
  onReview,
}: {
  review: ScriptReview | null;
  current: boolean;
  busy: boolean;
  onReview: () => Promise<boolean>;
}) {
  const [asking, setAsking] = useState(false);
  async function ask() {
    setAsking(true);
    await onReview();
    setAsking(false);
  }
  return (
    <section className={`content-review ${review && current ? (review.passed ? "is-passed" : "is-returned") : ""}`} aria-label="ARI's review">
      <h3>ARI&apos;s review</h3>
      {!review ? (
        <p className="hub-quiet">Not reviewed yet. ARI checks it against that day&apos;s commits, the hook, the flow, and the length.</p>
      ) : !current ? (
        <p className="hub-quiet">You changed the script since ARI read it. Ask again.</p>
      ) : (
        <>
          <p className="content-verdict">
            {review.passed ? "Passed. Ready to approve." : "Returned with notes."}
            {review.hookScore ? <span> Hook {review.hookScore}/5 · Flow {review.flowScore}/5</span> : null}
          </p>
          {review.truth.length + review.rules.length + review.notes.length ? (
            <ul>
              {review.truth.map((note, index) => (
                <li key={`t${index}`} className="is-truth">
                  Not true to the day: {note}
                </li>
              ))}
              {review.rules.map((note, index) => (
                <li key={`r${index}`}>{note}</li>
              ))}
              {review.notes.map((note, index) => (
                <li key={`n${index}`}>{note}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
      <button type="button" className="content-edit" disabled={busy || asking} onClick={ask}>
        {asking ? "ARI is reading it…" : review && current ? "Review again" : "Ask ARI to review"}
      </button>
    </section>
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
