"use client";

import { useEffect, useState } from "react";

import type { BrainPanel } from "@/src/core/ari-spine/brain-bridge";

import { clock, greeting } from "./format";

type Event = NonNullable<BrainPanel["calendarToday"]>[number];

// The top of Today: what's happening now or next, ticking with the clock, then the
// rest of the day as a quiet strip.
export function NowHero({ events, name }: { events: Event[]; name: string }) {
  const now = useMinute();
  if (!now) {
    return <section className="now-hero" aria-label="Now" />;
  }
  const nowMs = now.getTime();
  const timed = events.filter((event) => !event.all_day).sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
  const current = timed.find((event) => Date.parse(event.start) <= nowMs && nowMs < Date.parse(event.end));
  const next = timed.find((event) => Date.parse(event.start) > nowMs);
  const focus = current ?? next;
  const after = focus ? timed.filter((event) => Date.parse(event.start) > Date.parse(focus.start)) : [];

  return (
    <section className="now-hero" aria-labelledby="now-title">
      {focus ? (
        <>
          <p className="now-eyebrow">
            {current ? `Now · until ${clock(current.end)}` : `Next · ${until(Date.parse(focus.start) - nowMs)}`}
          </p>
          <h1 id="now-title">
            {focus.title} <span className="now-at">at {clock(focus.start)}</span>
          </h1>
          <p className="now-sub">{afterLine(after)}</p>
        </>
      ) : (
        <>
          <p className="now-eyebrow">{now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</p>
          <h1 id="now-title">
            {greeting(now)}, {name}.
          </h1>
          <p className="now-sub">{timed.length ? "That's everything on the calendar today." : "Nothing on the calendar today."}</p>
        </>
      )}
      {events.length ? (
        <ol className="now-day" aria-label="Today's calendar">
          {events.map((event) => {
            const past = !event.all_day && Date.parse(event.end) <= nowMs;
            const isFocus = event.id === focus?.id;
            return (
              <li key={event.id} className={past ? "is-past" : isFocus ? "is-focus" : ""}>
                <time>{event.all_day ? "All day" : clock(event.start)}</time>
                <span>{event.title}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}

function afterLine(after: Event[]): string {
  if (!after.length) {
    return "Nothing after that today.";
  }
  const [first, ...rest] = after;
  const more = rest.length ? `, and ${rest.length} more` : "";
  return `Then ${first.title} at ${clock(first.start)}${more}.`;
}

function until(ms: number): string {
  const minutes = Math.max(1, Math.round(ms / 60_000));
  if (minutes < 60) {
    return `in ${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `in ${hours} hr${rest ? ` ${rest} min` : ""}`;
}

function useMinute(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 20_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}
