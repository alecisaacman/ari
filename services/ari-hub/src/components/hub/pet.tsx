"use client";

import { useEffect, useState } from "react";

// ARI's pet: a small owl that shows how ARI is doing. It thinks while ARI writes a
// reply, perks up when something needs Alec, and sleeps when ARI is paused or late
// at night. Clicking it says what's going on in one line.

type Mood = "idle" | "thinking" | "alert" | "asleep";

export const THINKING_EVENT = "ari:thinking";

export function AriPet({ paused, needsYou }: { paused: boolean; needsYou: number }) {
  const [thinking, setThinking] = useState(false);
  const [late, setLate] = useState(false);
  const [saying, setSaying] = useState<string | null>(null);

  useEffect(() => {
    const onThinking = (event: Event) => setThinking(Boolean((event as CustomEvent<boolean>).detail));
    window.addEventListener(THINKING_EVENT, onThinking);
    const checkHour = () => {
      const hour = new Date().getHours();
      setLate(hour >= 23 || hour < 6);
    };
    checkHour();
    const timer = window.setInterval(checkHour, 60_000);
    return () => {
      window.removeEventListener(THINKING_EVENT, onThinking);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!saying) {
      return;
    }
    const timer = window.setTimeout(() => setSaying(null), 3500);
    return () => window.clearTimeout(timer);
  }, [saying]);

  const mood: Mood = thinking ? "thinking" : paused || late ? "asleep" : needsYou > 0 ? "alert" : "idle";
  const line =
    mood === "thinking"
      ? "Thinking..."
      : paused
        ? "I'm paused. Say \"ARI resume\" when you want me."
        : late
          ? "Resting. Text me if you need anything."
          : needsYou > 0
            ? `${needsYou} ${needsYou === 1 ? "thing needs" : "things need"} you.`
            : "All quiet. I'm watching.";

  return (
    <button
      type="button"
      className={`hub-pet hub-pet-${mood}`}
      onClick={() => setSaying(line)}
      aria-label={`ARI's owl: ${line}`}
      title={line}
    >
      {saying ? <span className="hub-pet-says">{saying}</span> : null}
      <svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true">
        <ellipse className="pet-shadow" cx="32" cy="60" rx="14" ry="2.5" />
        <g className="pet-body">
          <path className="pet-tuft" d="M17 19 L14 7 L25 15 Z" />
          <path className="pet-tuft" d="M47 19 L50 7 L39 15 Z" />
          <ellipse className="pet-wing pet-wing-l" cx="14.5" cy="38" rx="5" ry="11" />
          <ellipse className="pet-wing pet-wing-r" cx="49.5" cy="38" rx="5" ry="11" />
          <ellipse className="pet-fill" cx="32" cy="35" rx="18" ry="21" />
          <ellipse className="pet-belly" cx="32" cy="43" rx="11" ry="11" />
          <path className="pet-chevron" d="M28 40 l2 2 l2 -2 l2 2 l2 -2 M28 45 l2 2 l2 -2 l2 2 l2 -2" />
          <g className="pet-eyes">
            <circle className="pet-eye" cx="24.5" cy="28" r="7.2" />
            <circle className="pet-eye" cx="39.5" cy="28" r="7.2" />
            <g className="pet-look">
              <circle className="pet-pupil" cx="24.5" cy="28.5" r="3.4" />
              <circle className="pet-pupil" cx="39.5" cy="28.5" r="3.4" />
              <circle className="pet-glint" cx="25.8" cy="27" r="1" />
              <circle className="pet-glint" cx="40.8" cy="27" r="1" />
            </g>
            <g className="pet-lids">
              <rect x="16" y="20" width="17" height="16" rx="8" />
              <rect x="31" y="20" width="17" height="16" rx="8" />
            </g>
          </g>
          <path className="pet-beak" d="M29.5 34 L34.5 34 L32 38.5 Z" />
          <ellipse className="pet-foot" cx="27" cy="56" rx="3.2" ry="1.6" />
          <ellipse className="pet-foot" cx="37" cy="56" rx="3.2" ry="1.6" />
        </g>
        <g className="pet-zzz">
          <text x="47" y="14">z</text>
          <text x="53" y="8">z</text>
        </g>
        <circle className="pet-badge" cx="51" cy="20" r="4" />
      </svg>
    </button>
  );
}
