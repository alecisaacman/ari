# ARI Telegram Gateway

The ARI Telegram Gateway is a polling intake surface for natural-language ARI commands. Telegram is only the input surface. ARI remains the structured brain, router, memory, and authority layer.

## Current Bot

- Name: ARI Command
- Username: `@AriCommandBot`
- Bot identity: `ari_command`
- Current launch mode: private chat, polling, one authorized sender

The code is not designed around a one-bot-only assumption. Each event carries bot identity, source identity, conversation identity, sender identity, role assignment, and intent so future visible Telegram bots or a boardroom-style group can route into the same ARI event/state model.

## Architecture

- `ari_telegram_gateway.agent_registry`: role registry for CEO, CPO, CTO_CODEX, CCO, RESEARCH, MEMORY, and OPERATOR.
- `ari_telegram_gateway.classifier`: deterministic natural-language role and intent classification.
- `ari_telegram_gateway.event_builder`: conversion from Telegram-like updates into structured ARI events.
- `ari_telegram_gateway.persistence`: local JSON persistence for raw inbox updates, structured events, and pending Codex tasks.
- `ari_telegram_gateway.asset_saver`: Telegram file download boundary for photos, videos, documents, and voice notes.
- `ari_telegram_gateway.polling`: polling service using the Telegram Bot API.
- `ari_telegram_gateway.transcription`: placeholder seam for a future local `whisper.cpp` transcription worker.

## Environment

Create a local `.env` file. Do not commit it.

```bash
TELEGRAM_BOT_TOKEN=replace-with-botfather-token
AUTHORIZED_TELEGRAM_USER_ID=replace-with-your-numeric-telegram-user-id
ARI_TELEGRAM_INBOX_DIR=data/telegram/inbox
ARI_TELEGRAM_EVENTS_DIR=data/telegram/events
ARI_TELEGRAM_BOT_IDENTITY=ari_command
```

Optional:

```bash
ARI_TELEGRAM_POLLING_TIMEOUT_SECONDS=30
ARI_TELEGRAM_POLLING_STATE_FILE=data/telegram/state/ari_command_polling_state.json
```

`data/telegram/` is ignored local runtime data. It can contain raw Telegram payloads,
structured ARI events, downloaded assets, pending Codex task records, and polling state.
Do not commit `.env` or anything under `data/telegram/`.

## Create A Telegram Bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Choose the display name, for example `ARI Command`.
4. Choose the username, for example `AriCommandBot`.
5. Store the token in local `.env` as `TELEGRAM_BOT_TOKEN`.
6. Keep conservative BotFather settings for launch if desired:
   - group joining disabled
   - privacy mode enabled
   - inline mode disabled
   - inline geo disabled

These settings are not architectural assumptions. The gateway can later support group conversations and multiple visible bot identities.

## Find Your Authorized Telegram User ID

1. Send any message to `@AriCommandBot`.
2. Run this locally, replacing the token value without printing it into logs:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

3. In the JSON response, find `message.from.id`.
4. Put that numeric value in `.env` as `AUTHORIZED_TELEGRAM_USER_ID`.

Never commit `.env`.

## Run Locally In Dev Mode

The reliable no-install command from the repo root is:

```bash
PYTHONPATH=packages/ari-telegram-gateway/src ./.venv312/bin/python -m ari_telegram_gateway.polling
```

For a bounded live check:

```bash
PYTHONPATH=packages/ari-telegram-gateway/src ./.venv312/bin/python -m ari_telegram_gateway.polling --max-updates 3
```

`--max-updates` is for testing only. Do not use it for the persistent local
service, because it exits after the configured number of updates.

The `ari-telegram-gateway` console script exists after the project is installed into the
active virtual environment. If `./.venv312/bin/ari-telegram-gateway` is missing, refresh
the editable install:

```bash
./.venv312/bin/pip install -e .
```

Then run:

```bash
./.venv312/bin/ari-telegram-gateway
```

## Persistent Local Service

Use the local service scripts from the repo root when the gateway should stay
available while the Mac is on:

```bash
scripts/telegram_gateway/start.sh
scripts/telegram_gateway/status.sh
scripts/telegram_gateway/logs.sh
scripts/telegram_gateway/stop.sh
```

`start.sh`:

- refreshes the editable install with
  `./.venv312/bin/python -m pip install -e . --no-build-isolation`
- starts `./.venv312/bin/ari-telegram-gateway` without `--max-updates`
- writes logs to `data/telegram/logs/gateway.log`
- writes the PID file to `data/telegram/run/gateway.pid`
- refuses to start a duplicate gateway process
- does not print `TELEGRAM_BOT_TOKEN` or `.env`

`stop.sh` stops the PID in `data/telegram/run/gateway.pid` and removes stale or
invalid PID files cleanly.

`status.sh` reports whether the gateway is running, the PID when available, the
latest polling state, and recent log lines.

`logs.sh` tails:

```text
data/telegram/logs/gateway.log
```

Runtime data remains local and ignored:

```text
data/telegram/events/
data/telegram/inbox/
data/telegram/logs/
data/telegram/run/
data/telegram/state/
```

The service scripts do not send applications, emails, LinkedIn messages, or any
external contact. Telegram commands remain the same as the gateway code path.

## Surface Status Writes

The gateway writes local ACE surface status after processing Telegram updates
and after Career Command command handling.

Default files:

```text
data/surface/status/current.json
data/surface/status/history/<status_id>.json
```

These files are ignored local runtime state. Future ACE surfaces such as the
desktop companion, Inspection Cabinet, dashboards, and content intake surfaces
can read `current.json` to understand what ARI is doing now.

See [Surface Status](surface-status.md) for the model, mappings, and safety
boundaries.

## Career Command Operations

Career Command remains the existing sandbox at `~/code/openai-dev-sandbox`.
Telegram is the ACE phone surface for controlled local operations; it is not a
new job-search engine.

Supported commands:

```text
/career help
/career status
/career tracker
/career pending
/career latest
/career dashboard
/career scout_preview
/career save <rows>
/career draft <rows>
/career approve <pending_id_or_filename>
/career reject <pending_id_or_filename>
```

Operating loop:

1. `/career scout_preview` runs scout, extraction, and batch evaluation with
   `--limit 5`, then stops.
2. `/career latest` reviews the latest scout and batch output.
3. `/career save <rows>` saves selected batch rows into the local tracker only.
4. `/career draft <rows>` creates local pending outreach drafts only.
5. `/career pending` lists pending draft filenames and titles.
6. `/career approve <pending_id_or_filename>` or `/career reject
   <pending_id_or_filename>` updates local approval state only.

Approval is local state only. It moves a pending markdown file into
`approved_actions/` or `rejected_actions/` and appends the sandbox action log. It
does not send email, send LinkedIn messages, apply to jobs, contact anyone, or
run browser automation.

Only allowlisted Career Command scripts can run from Telegram. Telegram input is
never treated as arbitrary shell.

## Optional macOS LaunchAgent

A local LaunchAgent plist can be generated later, but it is disabled by default
and is not loaded automatically:

```bash
scripts/telegram_gateway/install_launch_agent.sh
```

The generator writes:

```text
~/Library/LaunchAgents/com.alecisaacman.ari.telegram-gateway.plist
```

To enable it explicitly:

```bash
launchctl load ~/Library/LaunchAgents/com.alecisaacman.ari.telegram-gateway.plist
```

To disable it:

```bash
launchctl unload ~/Library/LaunchAgents/com.alecisaacman.ari.telegram-gateway.plist
```

The LaunchAgent points at `scripts/telegram_gateway/start.sh` with this repo as
the working directory. It still relies on the local `.env`, ignored runtime
directories, and the same duplicate-process guard.

## Smoke Test Without Telegram Access

The smoke test converts a Telegram-like payload into the same structured event model without contacting Telegram:

```bash
PYTHONPATH=packages/ari-telegram-gateway/src ./.venv312/bin/python scripts/dev/smoke_telegram_gateway.py
```

It emits a structured event and writes JSON under configured directories or a temporary smoke directory.

## Polling State And Idempotency

The gateway persists Telegram polling state at
`data/telegram/state/ari_command_polling_state.json` unless
`ARI_TELEGRAM_POLLING_STATE_FILE` overrides it. The state stores:

- `last_processed_update_id`
- `updated_at`
- `bot_identity`

On startup, polling resumes at `last_processed_update_id + 1`. After an update is fully
processed and the confirmation reply is sent, the gateway persists the processed
`update_id`. If Telegram returns an update ID that has already been processed, the
gateway skips event creation, pending Codex task creation, asset saving, and Telegram
replying.

To reset local polling state:

```bash
rm data/telegram/state/ari_command_polling_state.json
```

Resetting state can cause Telegram to return older unacknowledged updates. Existing
structured event files are still used as an idempotency guard, but clearing
`data/telegram/events/` removes that local duplicate-protection history too.

## Event Behavior

Every authorized inbound message becomes a JSON event like:

```json
{
  "source": "telegram",
  "bot_identity": "ari_command",
  "conversation_id": "123456789",
  "sender_id": "123456789",
  "authorized": true,
  "raw_text": "Codex needs to inspect why dashboard buttons disappeared",
  "normalized_intent": "codex_task",
  "assigned_role": "CTO_CODEX",
  "risk_level": "medium",
  "requires_approval": true,
  "assets": [],
  "status": "received",
  "next_action": "create_pending_codex_task"
}
```

Code-related messages create a separate pending Codex task JSON with approval required. The gateway does not execute Codex, pass shell commands through, or modify code automatically.

Instagram links are stored as link-only assets:

- `source_platform`: `instagram`
- `media_status`: `link_only`
- `transcript_status`: `unavailable`
- `next_action`: `request_video_file_or_screen_recording_if_needed`

Uploaded video and voice files are saved locally when running against Telegram and marked with `transcript_status: pending`. Transcription is intentionally not implemented yet.

## Future Multi-Agent Expansion

The gateway can expand without changing the core event model:

- Multiple Telegram bots can set different `ARI_TELEGRAM_BOT_IDENTITY` values while writing into the same ARI event directories or future event bus.
- A Telegram boardroom group can route messages by sender, chat, thread, explicit role names, and bot identity while still creating one canonical ARI event per inbound message.
- Visible Telegram personas such as ARI CEO, CPO, CTO/Codex, CCO, Research, Operator, and Memory should stay role-based operators under ARI, not separate brains.
- Execution engines remain downstream workers. Telegram captures intent; ARI decides, persists, routes, and requests approval where required.
