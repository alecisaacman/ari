# ARI — Local-First Operational Intelligence

ARI is a local-first personal intelligence system for structured execution, memory, decision support, and approval-gated automation.

**ARI is the brain. ACE is the interface.**

## Core Identity

This repository contains the current canonical implementation of ARI's local-first brain and runtime.

ARI is designed to operate across surfaces and devices, beginning with the user's primary computer as the execution host. The code in this repository is the source-of-truth implementation for ARI's core loop, decision system, state model, and execution boundaries.

## What this repository contains

- `services/ari-core` — canonical runtime / brain
- `services/ari-api` — API contract over canonical capabilities
- `services/ari-hub` — ACE hub surface
- `packages/ari-telegram-gateway` — Telegram natural-language intake surface

## Current capabilities

ARI currently includes:

- canonical notes, tasks, and structured memory
- canonical coordination and policy state
- API-first hub-to-brain architecture
- bounded coding/operator execution
- execution lifecycle tracking and verification
- governed decision, dispatch, evaluation, and persistence loop
- typed signal decisions: act, escalate, defer, or ignore, with explicit reasoning
- local-first worker backend seam controlled by ARI, with deterministic stub and command-backed modes
- bounded self-improvement runner over the same worker seam
- single outward `ari` CLI entrypoint with natural-language routing
- self-improvement slice selection tied to repo state and execution intent
- verification profiles based on changed paths, expected symbols, targeted tests, output checks, and unexpected-change detection
- persisted controller decision records for bounded self-improvement cycles
- bounded action plans that give worker agents concrete local tasks, structural targets, and retry guidance
- Telegram polling gateway foundation that converts private natural-language Telegram messages into structured ARI events, role assignments, assets, and pending local tasks

## Current milestone

**v0.12 — Bounded action generation**

This means:

- the canonical brain/runtime is real
- the API seam is real
- the hub is a surface, not the brain
- execution exists as a bounded, policy-aware capability
- ARI can invoke worker agents inside its own controlled loop
- the terminal surface starts from one outward identity: `ari`
- ARI leaves a typed controller trail for bounded self-improvement cycles
- bounded self-improvement does not trust plausible stdout alone
- ARI generates explicit bounded action plans and tighter retry prompts for worker runs
- ARI can switch between stub and command-backed worker backends without changing the controller loop or outward interface

## Next milestone

**v1.0 — Governed autonomous coding loop**

Goal:

- generate bounded coding actions
- execute them under policy
- verify results
- retry intelligently
- reduce dependence on external coding agents for well-scoped local tasks over time

## Direction

Long-term, ARI is being built toward:

- durable local execution memory
- persistent self-documentation
- multi-surface access
- explicit inspection and review tools
- clean mobile and desktop access points

## Local-first execution model

ARI is designed as a local-first system.

Primary execution host:

- The user's local computer is the main execution environment.
- File access, command execution, and state mutation occur locally by default.

Future extension:

- Additional nodes such as mobile devices, remote workers, and cloud services may interface with the canonical brain.
- These nodes act as surfaces or extensions, not replacements for the core runtime.

Local-first does not mean single-machine forever. It means:

- local control
- local execution by default
- external systems are optional extensions, not dependencies

## Repository layout

- `services/ari-core/`
- `services/ari-api/`
- `services/ari-hub/`
- `packages/ari-telegram-gateway/`
- `config/schema.sql`
- `tests/`
- `docs/`

## Telegram gateway

The Telegram gateway is the first mobile natural-language command intake surface for ARI. Telegram captures user intent; ARI remains the brain, memory, router, and authority layer.

Setup:

1. Message `@BotFather` in Telegram and create the `ARI Command` bot, for example `@AriCommandBot`.
2. Add the local bot token to `.env` as `TELEGRAM_BOT_TOKEN`. Never commit `.env`.
3. Send a message to the bot, then call Telegram `getUpdates` to find `message.from.id`:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

4. Add the authorized sender and local data directories to `.env`:

```bash
AUTHORIZED_TELEGRAM_USER_ID=replace-with-your-numeric-telegram-user-id
ARI_TELEGRAM_INBOX_DIR=data/telegram/inbox
ARI_TELEGRAM_EVENTS_DIR=data/telegram/events
ARI_TELEGRAM_BOT_IDENTITY=ari_command
```

5. Run locally:

```bash
PYTHONPATH=packages/ari-telegram-gateway/src ./.venv312/bin/python -m ari_telegram_gateway.polling --max-updates 3
```

The console script is also available after `./.venv312/bin/pip install -e .`:

```bash
./.venv312/bin/ari-telegram-gateway --max-updates 3
```

The gateway writes ignored local runtime data under `data/telegram/`, including polling state at `data/telegram/state/ari_command_polling_state.json`. Delete that state file to reset the local Telegram offset. Never commit `.env` or `data/telegram/`.

Smoke test without Telegram live access:

```bash
PYTHONPATH=packages/ari-telegram-gateway/src ./.venv312/bin/python scripts/dev/smoke_telegram_gateway.py
```

See [docs/telegram-gateway.md](docs/telegram-gateway.md) for architecture, safety rules, BotFather setup, and future multi-bot or group expansion.

## Working rule

Keep ARI canonical.
Keep ACE thin.
Keep external providers pluggable.
If a capability belongs to the brain, move it inward.

## Surface simplicity

ARI is the outward identity.

The terminal-facing default should be:

- one invocation surface
- one response contract
- one canonical authority

External coding agents are workers under ARI's control, not the controller of the system. The worker seam is pluggable, but the controller remains canonical inside ARI.
