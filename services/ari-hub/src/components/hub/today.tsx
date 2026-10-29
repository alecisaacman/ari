import type { BrainPanel } from "@/src/core/ari-spine/brain-bridge";

import { HubChat } from "./chat";
import { when } from "./format";
import { NowHero } from "./now";

type Build = NonNullable<BrainPanel["builds"]>[number];

const BUILD_ORDER = ["building", "built", "stuck", "shipping", "approved", "proposed", "held"];
const BUILD_LABEL: Record<string, string> = {
  building: "Building now",
  built: "Ready to ship",
  stuck: "Stuck",
  shipping: "Shipping",
  approved: "Approved · next to build",
  proposed: "Proposed · waiting for your yes",
  held: "On hold",
};

// Today: what's now and next, three things worth a glance, and ARI to talk to.
export function Today({ panel, name }: { panel: BrainPanel; name: string }) {
  const apple = panel.apple ?? { connected: false, error: null };
  const appleDown = !apple.connected ? "Reminders and Calendar aren't connected." : apple.error ? "Reminders and Calendar didn't answer." : null;
  const getDone = panel.getDone ?? [];
  const [first, ...rest] = getDone;
  const build = topBuild(panel.builds ?? []);

  return (
    <div className="now">
      <NowHero events={panel.calendarToday ?? []} name={name} />
      {appleDown ? <p className="now-note">{appleDown}</p> : null}

      <div className="now-tiles">
        <section className="tile" aria-labelledby="tile-getdone">
          <h2 id="tile-getdone">Get done</h2>
          {first ? (
            <>
              <p className="tile-main">{first.title}</p>
              <p className="tile-sub">{first.due ? `Due ${when(first.due)}` : rest.length ? `${rest.length} more on the list` : "The only thing on the list"}</p>
              {rest.length ? (
                <details className="tile-more">
                  <summary>See all {getDone.length}</summary>
                  <ul>
                    {rest.map((item) => (
                      <li key={item.id}>
                        {item.title}
                        {item.due ? <em>{when(item.due)}</em> : null}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          ) : (
            <p className="tile-main is-calm">All clear</p>
          )}
        </section>

        <Noticed panel={panel} />

        <section className="tile" aria-labelledby="tile-build">
          <h2 id="tile-build">{build ? BUILD_LABEL[build.status] ?? build.status : "Building"}</h2>
          {build ? (
            <>
              <p className="tile-main">{build.title}</p>
              <p className="tile-sub tile-clamp">{build.result || build.why}</p>
            </>
          ) : (
            <>
              <p className="tile-main is-calm">Nothing approved yet</p>
              <p className="tile-sub">The morning and night reviews propose builds.</p>
            </>
          )}
        </section>
      </div>

      <HubChat initial={panel.conversations.hub} />
    </div>
  );
}

// The one thing ARI would bring up first: something waiting on Alec, then an alert,
// then the next timed reminder.
function Noticed({ panel }: { panel: BrainPanel }) {
  const waiting = panel.waitingForApproval[0];
  const alert = panel.alerts.find((item) => item.status !== "dismissed");
  const reminder = panel.reminders[0];
  const [label, main, sub] = waiting
    ? ["Waiting for you", waiting.summary, "Reply yes or no to ARI"]
    : alert
      ? ["ARI noticed", alert.title, alert.sentAt ? `Texted to you ${when(alert.sentAt)}` : "Not sent to your phone"]
      : reminder
        ? ["Reminder", reminder.text, when(reminder.remind_at)]
        : ["ARI noticed", null, "Nothing needs you right now."];
  return (
    <section className={`tile ${waiting ? "is-waiting" : ""}`} aria-labelledby="tile-noticed">
      <h2 id="tile-noticed">{label}</h2>
      {main ? <p className="tile-main">{main}</p> : <p className="tile-main is-calm">All quiet</p>}
      <p className="tile-sub tile-clamp">{sub}</p>
    </section>
  );
}

function topBuild(builds: Build[]): Build | undefined {
  return [...builds].sort((a, b) => rank(a.status) - rank(b.status))[0];
}

function rank(status: string): number {
  const index = BUILD_ORDER.indexOf(status);
  return index === -1 ? BUILD_ORDER.length : index;
}
