# ARI on iMessage, One Brain, and the Hub as a Window

Date: 2026-10-28
Covers: 2026-10-20 to 2026-10-28

## What changed

- **iMessage is the primary surface** (Oct 20–27). A launchd job snapshots my
  self-thread read-only; the gateway sends each new message to ARI's brain and texts the
  reply back. Late replies explain why they're late, and ARI never answers its own
  messages (an echo loop on the first night led to exact-text matching and a circuit
  breaker that pauses ARI after 30 model requests in 10 minutes).
- **One brain with cost-aware routing** (Oct 20–26). A fast model answers first and
  hands research, drafting, and judgment to a larger one. Requests are cached, every
  request is costed, and a monthly budget (default $10) stops model calls. The eval
  passed 20 of 20 realistic messages both routed and on the larger model alone, at
  roughly a third of the larger model's monthly cost.
- **Connected to ARI's records** (Oct 27). The brain remembers and recalls through ARI's
  memory and notes, records daily and weekly state, and the deterministic signal engine
  runs every 30 minutes without calling a model.
- **Reminders, one loop per thing, honest alerts** (Oct 28). Timed reminders are texted
  when due. Talking about an open loop again adds a dated note to it instead of filing
  it twice. The signal engine dismisses alerts that are no longer true, so a check-in
  recorded before 7 AM cancels the "you haven't checked in" text.
- **The hub is a window into the brain** (Oct 28). The hub's own model, intent detector,
  and background thinking were removed. It shows ARI's control panel and its chat box
  goes to the same conversation logic as iMessage.

## Underneath

The execution work from Sep 30 to Oct 20 (durable execution ledger, worker session
recovery, dispatch fences, capability-based execution, runtime convergence onto the
gateway) is what lets ARI propose a change, wait for approval, and run it exactly once.

## Verification

- Python suite: 934 passed; Ruff clean.
- Hub suite: 20 passed; the hub page was checked in a browser at desktop and phone width.

## Known limits

- ARI runs while the Mac is awake; replies and reminders wait while it sleeps.
- Each surface keeps its own conversation thread; memory, loops, state, and reminders
  are shared.
