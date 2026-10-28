import type { ReactNode } from "react";

export function Card({
  title,
  meta,
  empty,
  emptyText = "Nothing here.",
  className = "",
  children,
}: {
  title: string;
  meta?: string;
  empty?: boolean;
  emptyText?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <section className={`hub-card ${className}`}>
      <header className="hub-card-head">
        <h2>{title}</h2>
        {meta ? <span className="hub-card-meta">{meta}</span> : null}
      </header>
      {empty ? <p className="hub-quiet">{emptyText}</p> : children}
    </section>
  );
}
