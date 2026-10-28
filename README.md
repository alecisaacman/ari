# ARI

ARI is a local-first personal intelligence system. It runs on my own machine, keeps its
own memory, notices what needs attention, and acts only under explicit policy, with
approval before anything that changes the world outside its own records.

**ARI is the brain. ACE is how it shows up across surfaces.**

## What ARI does today

- **Talks over iMessage.** I text my own thread; ARI reads it, thinks, and replies.
  No separate app, and no second brain on any surface.
- **Remembers.** People, preferences, goals, and notes go into ARI's own store and are
  recalled before it answers. Memory lives in ARI, never in a model.
- **Keeps one list.** Tasks, commitments, and job applications become open loops.
  Mentioning something again adds to the loop that's already open instead of filing
  it twice.
- **Reminds.** "Remind me at 3 to call Sam" is texted back at 3, with no model call.
- **Notices on its own.** A deterministic signal engine checks every 30 minutes for
  piling-up or stale loops, a drifting week, high stress, or a missed check-in, and
  texts only what's still true.
- **Asks before acting.** Changes to files or running commands are proposed, approved
  with a "yes", and executed once through a durable execution gateway.
- **Shows its insides.** The hub is a control panel into the same brain: today, the
  week, open loops with their history, reminders, alerts and why they fired, memory,
  conversations, and spend.

## How it thinks, and what that costs

One brain (`services/ari-core/src/ari_core/brain.py`) answers every surface. A small,
fast model handles routine messages and hands anything that needs research, drafting,
or judgment to a larger one. Every request is cached and costed, and a monthly budget
stops model calls before it's exceeded. A built-in eval compares the routing against
the larger model alone on realistic messages; see
[docs/imessage-surface.md](docs/imessage-surface.md) for the numbers.

## What's here

| Path | Role |
|---|---|
| `services/ari-core` | The brain and canonical runtime: conversation, memory, state, signals, reminders, execution |
| `services/ari-api` | HTTP API over `ari-core`, including the control panel (`/brain/panel`) |
| `services/ari-hub` | The hub: a window into ARI, with a chat box to the same brain |
| `packages/ari-imessage-gateway` | iMessage surface (macOS): carries texts in and out |
| `packages/ari-memory` | ARI's local store (SQLite by default) |
| `packages/ari-telegram-gateway` | Telegram intake, an earlier surface kept for reference |
| `evals/brain` | Model-routing quality and cost eval |

## Design principles

- **One brain.** Every surface talks to the same conversation logic and records.
  Nothing lives only in a surface.
- **Records over recollection.** ARI's state is stored and read back, not remembered by
  a model.
- **Bounded execution.** ARI acts under policy: typed decisions, approvals decided in
  code from my own words, verified results, and a persisted trail for every step.
- **Durable continuity.** Execution tasks, attempts, ordered events, append-only
  checkpoints, and normalized results live independently of the worker that ran them.
- **Fix it where it lives.** When something is wrong, it's fixed in the component that
  owns the truth, not filtered downstream.
- **Local-first, not local-only.** My machine is the primary host today. Other surfaces
  extend the brain; they never replace it.

## Getting started

```bash
pip install -e .
ari --help
```

The iMessage surface needs macOS and a few one-time permissions; see
[docs/imessage-surface.md](docs/imessage-surface.md). Secrets and personal identifiers
live in a private env file outside the repository, never in it.

## Status and history

ARI is under active development. Progress notes are in [docs/progress/](docs/progress/),
and directions tried and set aside are in [docs/paths-explored.md](docs/paths-explored.md).

## Security

See [SECURITY.md](SECURITY.md).
