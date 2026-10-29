"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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

// How fresh the view is: "Live" just after a read, then the seconds since.
export function Freshness({ generatedAt }: { generatedAt: string }) {
  const now = useNow(5_000);
  const age = now ? Math.max(0, Math.round((now.getTime() - Date.parse(generatedAt)) / 1000)) : 0;
  return <span className="hub-fresh">{age < 45 ? "Live" : `Updated ${age < 120 ? `${age}s` : `${Math.round(age / 60)}m`} ago`}</span>;
}
