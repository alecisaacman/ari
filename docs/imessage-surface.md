# iMessage Surface

ARI has one brain: `ari_core/brain.py`. iMessage is an ACE surface. It relays
Alec's self-thread to that brain and sends the brain's replies back. It never
reasons on its own, and neither does any other surface.

## What a conversation can do

- **Ask.** "What's on my plate?" The brain answers from ARI's open loops, daily
  and weekly state, and the latest signals and alerts. It searches the web only
  when that changes the answer.
- **Capture.** Tasks, commitments, job applications (which start company
  research), and links to save for later go straight into ARI's records.
- **Remember.** Lasting facts about Alec, his people, and his work go into ARI's
  canonical memory (`remember`), longer material into notes (`save_note`), and
  the brain checks them (`recall`) before answering about a person or something
  said before. Recall matches word by word and ranks by how many words match.
- **Check in.** "Today I want to finish X, stress is a 6" is recorded as the day's
  priorities, win condition, and stress (`set_daily_state`), and the week's plan
  likewise (`set_weekly_plan`). Open loops include tasks created from the hub, so
  there is one view of what is on Alec's plate.
- **Act, with approval.** For anything outside ARI's own records (writing or
  patching a file in the workspace, or running tests), the brain proposes one
  action. ARI asks Alec. "yes" approves it, "no" cancels it, and "yes 2" picks
  from several. The approval is decided by ARI from Alec's reply, never by the
  model. The approved action runs once through the canonical execution gateway
  ([Runtime Execution Convergence](execution/runtime-convergence.md)), and ARI
  reports what happened.
- **Be noticed.** While ARI is running and not paused, the poller runs ARI's
  signal engine every 30 minutes. It is deterministic and costs nothing. It looks
  for open loops piling up, high-priority loops going stale, the week drifting
  from its outcomes, elevated stress, and no check-in for the day. Its alerts are
  sent as below; for the text, the gateway phrases them for a person (the
  engine's own wording stays in ARI's records), and only alerts about the current
  day are sent. Unattended runs may auto-execute only reads (`read_file`, `ls`,
  `cat`) in the workspace; anything else needs approval and does not run.
- **Hear from ARI.** Elevated, interruptive, and urgent alerts from the last day
  are texted once, with the reason ARI raised them. Quiet hours (default 22:00
  to 07:00) hold back everything but urgent alerts.
- **Stop it.** "ARI stop" pauses everything, including execution. "ARI resume"
  resumes. Messages sent while paused are not acted on.
- **Watch the cost.** "ARI spend" reports this month's model spend against the
  budget. "ARI budget 15" sets the monthly budget to $15.

## Which model answers, and what it costs

Polling, alerts, approvals, and the text commands above never call a model. Only
a message for the brain does.

- **Claude Haiku 5.5 answers first** (effort `low`). It reads and updates
  Alec's records: open loops, daily and weekly state, signals, saved links.
- **Claude Sonnet 5.5 takes over** (effort `medium`, with server-side refusal
  fallback) when Haiku calls `use_deeper_model`. Haiku does this for web lookups,
  research, drafting, planning, analysis, "why" questions, workspace changes, or
  anything it isn't confident about. Sonnet also takes messages Alec starts with
  `think:`, `research:`, or `deep:`, and messages over 600 characters. Sonnet
  answers the whole turn from a clean start; Haiku's abandoned attempt is not
  kept, but its cost is.
- **Every request is cached** (`cache_control`), so the system prompt, tools,
  and conversation so far cost a tenth of the input rate on repeat.
- **Every request is costed** from the usage the API reports and recorded in
  `brain_usage`. Before calling a model, the gateway checks the month's total
  against the budget ($10 by default, `ARI_BRAIN_MONTHLY_BUDGET_USD`, or "ARI
  budget N"). Over budget, ARI replies without calling a model. The message that
  crosses the line is the last one billed.
- The two models get different tools, and each model's thinking is bound to the
  request that produced it, so requests set
  `prefix_mismatch_behavior: "drop_block"`: after a model switch, the other
  model's reasoning is dropped instead of failing the request.

Measured on 2026-10-21 with `evals/brain/run_eval.py` (20 realistic messages,
each through the routed brain and through Sonnet alone; both passed 20/20). The
ranges run from a warm cache to a cold one:

| Message | Routed | Sonnet alone |
|---|---|---|
| Routine (state, capture, resolve) | $0.0005-0.0008 | $0.026-0.046 |
| Deeper, no web search | $0.031-0.054 | $0.030-0.054 |
| Deeper, with web search | $0.045-0.092 | $0.052-0.106 |

With 75% routine, 15% deeper, and 10% search messages, that is about $3 to $5 a
month at 10 messages a day and about $9 at 20, against about $25 for Sonnet
alone. Turns that need Sonnet are a quarter of messages and nearly all of the
cost; web search is the most expensive. The eval calls the real API, and
`--max-usd` caps what it can spend.

## How it works

```text
Messages.app ── chat.db
                  │  read-only, every 10 s
   launchd ── /usr/bin/sqlite3          (the only process with Full Disk Access)
                  │
            ARI_HOME/imessage/self-thread.tsv
                  │  every 10 s
   launchd ── python -m ari_imessage_gateway poll
                  │
          control → approvals → brain → reply (AppleScript) → alerts
```

macOS attributes a Full Disk Access check to the process launchd started, not to
the binary that opens the file. Tested on this Mac on 2026-06-19: a
`launchd → bash → sqlite3` chain was denied, and `launchd → sqlite3` succeeded. So
`/usr/bin/sqlite3` is launchd's direct child, and it is the only binary that ever
needs Full Disk Access.

A self-thread has one sender, so ARI's replies come back looking like Alec's
messages. The gateway recognizes them by their exact text. A message that fails
is retried on the next poll. Messages before it are never replayed, because the
cursor and conversation are saved after each message. On the first run the
gateway starts from the latest message and does not answer the thread's history.

Reply latency is up to about 20 seconds plus the model's response time.

## State

- ARI's records and the conversation live in `ARI_HOME/state/ari.db` (SQLite).
  Set `DATABASE_URL` to use Postgres instead. A SQLite store is built from the
  current table metadata, because the Alembic history alters constraints in a way
  SQLite cannot.
- Proposals and their approvals live in the execution ledger, as tasks waiting
  at the gateway's approval gate.
- The conversation history stays append-only so the brain's thinking stays
  valid. Past 60 messages it rolls to the most recent turns, and the thinking
  blocks are dropped once, at that boundary.

## Setup

ARI cannot do these steps itself. They grant permissions or hold secrets.

1. Create `~/ARI/ari.env` and run `chmod 600 ~/ARI/ari.env`. Set:
   - `ARI_IMESSAGE_TO`: your own phone number or Apple ID, the self-thread ARI
     replies into
   - `ARI_IMESSAGE_SELF_IDENTIFIERS`: every identifier your self-thread appears
     under, comma-separated (phone and Apple ID email)
   - `ANTHROPIC_API_KEY`, unless you use `ant auth login`
   - `ARI_EXECUTION_ROOT` (optional): a workspace folder for approved actions.
     It must not be the ARI checkout or `~/ARI`. Without it, ARI only answers and
     captures.
2. Check the setup: `ari-imessage doctor`.
3. Render the launchd jobs: `ari-imessage plists --out ~/ARI/imessage/launchd`.
   Review them, then copy both into `~/Library/LaunchAgents/` and load them with
   `launchctl bootstrap gui/$(id -u) <plist>`.
4. Grant Full Disk Access to `/usr/bin/sqlite3` only: System Settings → Privacy &
   Security → Full Disk Access. Add the binary itself, not Terminal or Python.
5. Run `ari-imessage send-test`, and allow Messages automation when macOS asks.
6. Text yourself "what's on my plate?"

To preview without sending or saving anything, run `ari-imessage poll --dry-run`.
It does call the model.

If Anthropic credits run out or the API key is rejected, ARI answers each message
with a plain explanation, written by its code with no model call, and does not
retry. A reply more than three minutes late is preceded by a notice of when the
message was sent and when ARI was last running.

## Limits

- One Apple ID means no separate "ARI" sender. ARI writes in your own
  self-thread.
- Workspace actions are limited to `write_file`, `patch_file`, and the `ls`,
  `cat`, `pytest`, and `node` command capabilities. Calendar, email, and other
  integrations are future ACE surfaces and tools.
- The hub keeps its own model path for web chat. It is not wired to this brain
  yet, so iMessage is the only surface that reaches ARI's brain today.
