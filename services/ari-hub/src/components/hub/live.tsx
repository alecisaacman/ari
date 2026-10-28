"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { greeting } from "./format";

// The hub stays current while it's on screen: ARI's panel is re-read every 30 seconds
// and whenever the window comes back into view. Reading the panel calls no model, so
// it costs nothing; nothing is read while the hub is hidden.
const REFRESH_MS = 30_000;

export function LiveRefresh() {
  const router = useRouter();

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") {
        router.refresh();
      }
    };
    const timer = window.setInterval(refresh, REFRESH_MS);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [router]);

  return null;
}

function useNow(everyMs: number): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), everyMs);
    return () => window.clearInterval(timer);
  }, [everyMs]);
  return now;
}

// The greeting, date, and time, ticking in the browser.
export function LiveHello({ name }: { name: string }) {
  const now = useNow(1_000);
  if (!now) {
    return (
      <div className="hub-hello">
        <p className="hub-date">&nbsp;</p>
        <h1>Hello, {name}</h1>
      </div>
    );
  }
  return (
    <div className="hub-hello">
      <p className="hub-date">
        {now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
        <span className="hub-clock">{now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</span>
      </p>
      <h1>
        {greeting(now)}, {name}
      </h1>
    </div>
  );
}

// How fresh the view is: "Live" just after a read, then the seconds since.
export function Freshness({ generatedAt }: { generatedAt: string }) {
  const now = useNow(5_000);
  const age = now ? Math.max(0, Math.round((now.getTime() - Date.parse(generatedAt)) / 1000)) : 0;
  return <span className="hub-fresh">{age < 45 ? "Live" : `Updated ${age < 120 ? `${age}s` : `${Math.round(age / 60)}m`} ago`}</span>;
}
