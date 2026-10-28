import type { BrainPanel } from "@/src/core/ari-spine/brain-bridge";

import { Card } from "./card";
import { HubChat } from "./chat";
import { clock, when } from "./format";

// The Today side: what's in front of Alec, and ARI to talk to.
export function Today({ panel }: { panel: BrainPanel }) {
  const apple = panel.apple ?? { connected: false, error: null };
  const appleNote = !apple.connected ? "not connected" : apple.error ? "didn't answer" : undefined;
  const calendar = panel.calendarToday ?? [];
  const getDone = panel.getDone ?? [];
  const nowMs = Date.parse(panel.generatedAt);
  const noticed = panel.alerts.filter((alert) => alert.status !== "dismissed");

  return (
    <div className="hub-today">
      <Card title="ARI" className="hub-chat-card">
        <HubChat initial={panel.conversations.hub} />
      </Card>

      <div className="hub-stack">
        <Card title="Today" meta={appleNote ?? `${calendar.length} on the calendar`} empty={!calendar.length} emptyText="Nothing on the calendar.">
          <ol className="hub-timeline">
            {calendar.map((event) => {
              const past = !event.all_day && Date.parse(event.end) < nowMs;
              const now = !event.all_day && Date.parse(event.start) <= nowMs && nowMs < Date.parse(event.end);
              return (
                <li key={event.id} className={past ? "is-past" : now ? "is-now" : ""}>
                  <time>{event.all_day ? "All day" : clock(event.start)}</time>
                  <div>
                    <strong>{event.title}</strong>
                    <span>
                      {event.calendar}
                      {event.location ? ` · ${event.location}` : ""}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>

        <Card title="GET DONE" meta={appleNote ?? `${getDone.length} open`} empty={!getDone.length} emptyText="All clear.">
          <ul className="hub-checklist">
            {getDone.map((item) => (
              <li key={item.id}>
                <span className="hub-check" aria-hidden="true" />
                <span>
                  {item.title}
                  {item.due ? <em>{when(item.due)}</em> : null}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        {panel.waitingForApproval.length ? (
          <Card title="Waiting for you" meta="say yes or no to ARI" className="hub-attention">
            <ul className="hub-list">
              {panel.waitingForApproval.map((item) => (
                <li key={item.taskId}>{item.summary}</li>
              ))}
            </ul>
          </Card>
        ) : null}

        <Card title="Reminders" empty={!panel.reminders.length} emptyText="No timed reminders.">
          <ul className="hub-list">
            {panel.reminders.map((reminder) => (
              <li key={reminder.id}>
                <strong>{reminder.text}</strong>
                <span>{reminder.remind_at}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="What ARI noticed" meta="last 2 days" empty={!noticed.length} emptyText="Nothing needs you.">
          <ul className="hub-list">
            {noticed.map((alert) => (
              <li key={alert.id}>
                <strong>{alert.title}</strong>
                <span>{alert.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
