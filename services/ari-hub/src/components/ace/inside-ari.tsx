import type { BrainPanel } from "@/src/core/ari-spine/brain-bridge";

import { AriChat } from "./ari-chat";

// A window into ARI's brain. Everything here is ARI's own record, read live;
// the hub computes none of it.

function when(value: string | null): string {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function Panel({ title, source, empty, children }: { title: string; source: string; empty: boolean; children: React.ReactNode }) {
  return (
    <article className="ace-readonly-panel">
      <div className="ace-readonly-panel-header">
        <h2>{title}</h2>
      </div>
      <p className="ace-readonly-source">{source}</p>
      {empty ? <p className="ace-readonly-empty">Nothing yet.</p> : children}
    </article>
  );
}

export function InsideAri({ panel, error }: { panel: BrainPanel | null; error: string | null }) {
  if (!panel) {
    return (
      <section className="ace-readonly-section" aria-labelledby="inside-ari-title">
        <h2 id="inside-ari-title">Inside ARI</h2>
        <p className="ace-readonly-warning">ARI's brain isn't reachable: {error ?? "unknown error"}. Start ari-api to see inside.</p>
      </section>
    );
  }

  const { today, week } = panel;
  const apple = panel.apple ?? { connected: false, error: null };
  const getDone = panel.getDone ?? [];
  const calendarToday = panel.calendarToday ?? [];
  const appleSource = (what: string) =>
    !apple.connected ? `${what}, not connected` : apple.error ? `${what}: ${apple.error}` : what;
  const conversation = [...panel.conversations.imessage.map((line) => ({ ...line, via: "iMessage" }))];

  return (
    <section className="ace-readonly-section" aria-labelledby="inside-ari-title">
      <div className="ace-readonly-section-heading">
        <div>
          <p className="ace-readonly-kicker">Live from ARI's brain, {when(panel.generatedAt)}</p>
          <h2 id="inside-ari-title">Inside ARI</h2>
        </div>
        <span className={`ace-readonly-status ace-readonly-status-${panel.paused.paused ? "disabled" : "active"}`}>
          {panel.paused.paused ? "paused" : "running"}
        </span>
      </div>
      {panel.paused.paused && panel.paused.reason ? <p className="ace-readonly-warning">{panel.paused.reason}</p> : null}

      <AriChat initial={panel.conversations.hub} />

      <section className="ace-readonly-metrics" aria-label="ARI at a glance">
        <div>
          <span>Open loops</span>
          <strong>{panel.openLoops.length + panel.hubTasks.length}</strong>
        </div>
        <div>
          <span>Reminders</span>
          <strong>{panel.reminders.length}</strong>
        </div>
        <div>
          <span>Waiting for you</span>
          <strong>{panel.waitingForApproval.length}</strong>
        </div>
        <div>
          <span>Stress today</span>
          <strong>{today?.stress ?? "-"}</strong>
        </div>
        <div>
          <span>Spend this month</span>
          <strong>
            ${panel.spend.spentUsd.toFixed(2)} / ${panel.spend.budgetUsd.toFixed(0)}
          </strong>
        </div>
      </section>

      <div className="ace-readonly-grid">
        <Panel title="Today" source="daily state" empty={!today}>
          <ul>
            {today?.priorities.map((priority) => <li key={priority}>{priority}</li>)}
            {today?.win_condition ? <li>Win: {today.win_condition}</li> : null}
            {today?.next_action ? <li>Next: {today.next_action}</li> : null}
          </ul>
        </Panel>

        <Panel title="This week" source="weekly state" empty={!week || !week.outcomes.length}>
          <ul>
            {week?.outcomes.map((outcome) => <li key={outcome}>{outcome}</li>)}
            {week?.blockers.map((blocker) => <li key={blocker}>Blocked: {blocker}</li>)}
          </ul>
        </Panel>

        <Panel title="Open loops" source="open loops and hub tasks" empty={!panel.openLoops.length && !panel.hubTasks.length}>
          <ul>
            {panel.openLoops.map((loop) => (
              <li key={loop.id}>
                <strong>{loop.title}</strong> ({loop.priority})
                {loop.notes ? <pre className="ace-ari-notes">{loop.notes}</pre> : null}
              </li>
            ))}
            {panel.hubTasks.map((task) => (
              <li key={`hub-${task.id}`}>{task.title}</li>
            ))}
          </ul>
        </Panel>

        <Panel title="Calendar today" source={appleSource("Apple Calendar")} empty={!calendarToday.length}>
          <ul>
            {calendarToday.map((event) => (
              <li key={event.id}>
                {event.all_day ? "All day" : new Date(event.start).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}:{" "}
                <strong>{event.title}</strong> ({event.calendar})
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="GET DONE" source={appleSource("Apple Reminders")} empty={!getDone.length}>
          <ul>
            {getDone.map((item) => (
              <li key={item.id}>
                {item.title}
                {item.due ? ` (due ${when(item.due)})` : ""}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Reminders" source="timed reminders ARI set" empty={!panel.reminders.length}>
          <ul>
            {panel.reminders.map((reminder) => (
              <li key={reminder.id}>
                {reminder.remind_at}: {reminder.text}
                {reminder.delivered_by ? ` (via ${reminder.delivered_by})` : ""}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="ARI's build list" source="what ARI wants to build next; say yes or hold to ARI" empty={!(panel.builds ?? []).length}>
          <ul>
            {(panel.builds ?? []).map((build) => (
              <li key={build.id}>
                <strong>{build.title}</strong> ({build.status})<br />
                {build.why}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Waiting for your approval" source="execution gateway" empty={!panel.waitingForApproval.length}>
          <ul>
            {panel.waitingForApproval.map((item) => (
              <li key={item.taskId}>{item.summary}</li>
            ))}
          </ul>
          <p className="ace-readonly-source">Approve or decline by saying "yes" or "no" to ARI.</p>
        </Panel>

        <Panel title="What ARI noticed" source="signal engine alerts, last 2 days" empty={!panel.alerts.length}>
          <ul>
            {panel.alerts.map((alert) => (
              <li key={alert.id}>
                <strong>{alert.title}</strong> ({alert.status}
                {alert.sentAt ? `, texted ${when(alert.sentAt)}` : ""})<br />
                Why: {alert.reason}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="What ARI remembers" source="canonical memory" empty={!panel.memories.length}>
          <ul>
            {panel.memories.map((memory) => (
              <li key={memory.id}>
                <strong>{memory.title}</strong>: {memory.content}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Notes" source="canonical notes" empty={!panel.notes.length}>
          <ul>
            {panel.notes.map((note) => (
              <li key={note.id}>
                <strong>{note.title}</strong>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="On iMessage" source="recent self-thread conversation" empty={!conversation.length}>
          <ul className="ace-ari-transcript">
            {conversation.map((line, index) => (
              <li key={index} className={`ace-ari-line ace-ari-line-${line.role}`}>
                <span>{line.role === "alec" ? "You" : "ARI"}</span> {line.text}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Model spend" source="brain usage" empty={false}>
          <p>{panel.spend.summary}</p>
        </Panel>
      </div>
    </section>
  );
}
