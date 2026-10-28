import type { ReactNode } from "react";

import type { BrainPanel } from "@/src/core/ari-spine/brain-bridge";

import { Card } from "./card";
import { when } from "./format";

type Skill = { skill_id: string; name: string; lifecycle_status: string };

const BUILD_ORDER: Record<string, number> = { approved: 0, proposed: 1, held: 2 };

// The ARI side: what ARI is working toward, how it reviews itself, and what it knows.
export function Inside({ panel, skills, underTheHood }: { panel: BrainPanel; skills: Skill[]; underTheHood: ReactNode }) {
  const builds = [...(panel.builds ?? [])].sort((a, b) => (BUILD_ORDER[a.status] ?? 9) - (BUILD_ORDER[b.status] ?? 9));
  const reviews = panel.notes.filter((note) => /review,/i.test(note.title)).slice(0, 2);
  const otherNotes = panel.notes.filter((note) => !/review,/i.test(note.title));
  const loops = [...panel.openLoops, ...panel.hubTasks.map((task) => ({ id: `hub-${task.id}`, title: task.title, priority: "", notes: task.notes }))];
  const spendShare = Math.min(1, panel.spend.spentUsd / Math.max(panel.spend.budgetUsd, 0.01));

  return (
    <div className="hub-inside">
      <section className="hub-builds" aria-labelledby="builds-title">
        <header className="hub-section-head">
          <h2 id="builds-title">What ARI wants to build</h2>
          <p>ARI proposes; you say yes or hold. It never starts on its own.</p>
        </header>
        {builds.length ? (
          <div className="hub-build-grid">
            {builds.map((build) => (
              <article key={build.id} className={`hub-build hub-build-${build.status}`}>
                <span className="hub-chip">{build.status}</span>
                <h3>{build.title}</h3>
                <p>{build.why}</p>
                <details>
                  <summary>Brief</summary>
                  <p>{build.brief}</p>
                </details>
              </article>
            ))}
          </div>
        ) : (
          <p className="hub-quiet">Nothing proposed yet. The morning and night reviews add here.</p>
        )}
      </section>

      <div className="hub-grid">
        <Card title="Latest reviews" meta="8:00 AM and 9:00 PM" empty={!reviews.length} emptyText="The first review arrives at 9:00 PM.">
          {reviews.map((review) => (
            <article key={review.id} className="hub-review">
              <h3>{review.title}</h3>
              <p>{review.body}</p>
            </article>
          ))}
        </Card>

        <Card title="Open loops" meta={`${loops.length}`} empty={!loops.length}>
          <ul className="hub-list">
            {loops.map((loop) => (
              <li key={loop.id}>
                <strong>
                  {loop.title}
                  {loop.priority === "high" || loop.priority === "critical" ? <span className="hub-chip hub-chip-hot">{loop.priority}</span> : null}
                </strong>
                {loop.notes ? <span className="hub-clamp">{loop.notes}</span> : null}
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Spend" meta="this month">
          <p className="hub-figure">
            ${panel.spend.spentUsd.toFixed(2)} <span>of ${panel.spend.budgetUsd.toFixed(0)}</span>
          </p>
          <div className="hub-meter" role="img" aria-label={`${Math.round(spendShare * 100)} percent of budget`}>
            <span style={{ width: `${Math.max(spendShare * 100, 1)}%` }} />
          </div>
          <p className="hub-quiet">{panel.spend.summary}</p>
        </Card>

        <Card title="What ARI remembers" empty={!panel.memories.length} emptyText="Nothing kept yet.">
          <ul className="hub-list">
            {panel.memories.map((memory) => (
              <li key={memory.id}>
                <strong>{memory.title}</strong>
                <span>{memory.content}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Notes" empty={!otherNotes.length} emptyText="No notes yet.">
          <ul className="hub-list">
            {otherNotes.map((note) => (
              <li key={note.id}>
                <strong>{note.title}</strong>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="On iMessage" meta={`as of ${when(panel.generatedAt)}`} empty={!panel.conversations.imessage.length}>
          <div className="hub-mini-thread">
            {[...panel.conversations.imessage].reverse().map((line, index) => (
              <div key={index} className={`hub-bubble hub-bubble-${line.role === "alec" ? "me" : "ari"}`}>
                {line.text}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Skills" meta={`${skills.filter((skill) => skill.lifecycle_status !== "candidate").length} working, ${skills.filter((skill) => skill.lifecycle_status === "candidate").length} to build`}>
          <ul className="hub-skills">
            {skills.map((skill) => (
              <li key={skill.skill_id} className={`hub-skill-${skill.lifecycle_status}`}>
                {skill.name}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <details className="hub-under">
        <summary>Under the hood</summary>
        {underTheHood}
      </details>
    </div>
  );
}
