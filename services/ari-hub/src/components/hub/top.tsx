import Link from "next/link";
import type { ReactNode } from "react";

type Place = "today" | "content" | "ari";

const PLACES: Array<{ id: Place; href: "/" | "/content" | "/?tab=ari"; label: string; creatorOnly: boolean }> = [
  { id: "today", href: "/", label: "Today", creatorOnly: false },
  { id: "content", href: "/content", label: "Content", creatorOnly: true },
  { id: "ari", href: "/?tab=ari", label: "Inside ARI", creatorOnly: true },
];

// The top of every hub page: ARI, the places to go, and how fresh the view is.
export function HubTop({
  active,
  creator,
  dot = "ok",
  status,
}: {
  active: Place;
  creator: boolean;
  dot?: "ok" | "paused" | "down";
  status?: ReactNode;
}) {
  return (
    <header className="hub-top">
      <Link href="/" className="hub-mark" aria-label="ARI, Today">
        <span className={`hub-dot ${dot === "ok" ? "" : `is-${dot}`}`} aria-hidden="true" />
        ARI
      </Link>
      <nav className="hub-tabs" aria-label="Hub">
        {PLACES.map((place) => (
          <Link
            key={place.id}
            href={place.href}
            className={active === place.id ? "is-on" : ""}
            aria-current={active === place.id ? "page" : undefined}
          >
            {place.label}
            {place.creatorOnly && !creator ? <Lock /> : null}
          </Link>
        ))}
      </nav>
      <span className="hub-status">{status}</span>
    </header>
  );
}

function Lock() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" aria-label="locked" role="img">
      <rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
