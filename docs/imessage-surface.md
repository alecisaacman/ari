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
- **Act, with approval.** For anything outside ARI's own records (writing or
  patching a file in the workspace, or running tests), the brain proposes one
  action. ARI asks Alec. "yes" approves it, "no" cancels it, and "yes 2" picks
  from several. The approval is decided by ARI from Alec's reply, never by the
  model. The approved action runs once through the canonical execution gateway
  ([Runtime Execution Convergence](execution/runtime-convergence.md)), and ARI
  reports what happened.
- **Hear from ARI.** Elevated, interruptive, and urgent alerts from the last day
  are texted once, with the reason ARI raised them. Quiet hours (default 22:00
  to 07:00) hold back everything but urgent alerts.
- **Stop it.** "ARI stop" pauses everything, including execution. "ARI resume"
  resumes. Messages sent while paused are not acted on.
- **Watch the cost.** "ARI spend" reports this month's model spend against the
  budget. "ARI budget 10" sets the monthly budget to $10.

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
  against the budget ($5 by default, `ARI_BRAIN_MONTHLY_BUDGET_USD`, or "ARI
  budget N"). Over budget, ARI replies without calling a model. The message that
  crosses the line is the last one billed.
- The two models get different tools, and each model's thinking is bound to the
  request that produced it, so requests set
  `prefix_mismatch_behavior: "drop_block"`: after a model switch, the other
  model's reasoning is dropped instead of failing the request.

Estimated, not measured: about $1 to $4 a month at 20 messages a day, depending
on how often messages need Sonnet. `evals/brain/run_eval.py` measures it. It
runs 20 realistic messages through the routed brain and through Sonnet alone,
against seeded state with every action as a dry run, and reports pass rates, cost,
latency, and each reply. It calls the real API, and `--max-usd` caps what it can
spend.

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

## Limits

- One Apple ID means no separate "ARI" sender. ARI writes in your own
  self-thread.
- Workspace actions are limited to `write_file`, `patch_file`, and the `ls`,
  `cat`, `pytest`, and `node` command capabilities. Calendar, email, and other
  integrations are future ACE surfaces and tools.
- The hub keeps its own model path for web chat. It is not wired to this brain
  yet, so iMessage is the only surface that reaches ARI's brain today.
