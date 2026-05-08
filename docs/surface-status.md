# ARI Surface Status

The Surface Status layer is the shared local status artifact for ACE surfaces.
It answers the basic question: what is ARI doing right now?

This is not a new UI and not a second ARI brain. It is a small local read model
that surfaces can consume.

## File Locations

The default store writes:

```text
data/surface/status/current.json
data/surface/status/history/<status_id>.json
```

`data/surface/` is ignored by Git. These files are local runtime state.

`current.json` is the latest status for lightweight surfaces. `history/` keeps
append-only status snapshots for debugging, demos, and future Inspection Cabinet
timelines.

The location can be overridden with:

```text
ARI_SURFACE_STATUS_DIR=/custom/local/path
```

## Model

The model lives in:

```text
packages/ari-surface-status/src/ari_surface_status/
```

Controlled state enum:

```text
idle
listening
thinking
working
waiting_for_approval
blocked
success
error
```

Controlled severity enum:

```text
info
warning
error
```

Each status includes:

- `status_id`
- `created_at`
- `state`
- `severity`
- `title`
- `message`
- `source`
- optional `surface`
- optional `event_id`
- optional `command`
- optional low-risk `metadata`

The status payload must not contain secrets, Telegram bot tokens, `.env`
contents, or API keys.

## Telegram Integration

The Telegram Gateway writes a status after normal event persistence.

Current mappings:

- unauthorized rejected event -> `blocked`
- `CTO_CODEX` with approval required -> `waiting_for_approval`
- CPO competitor or product signal -> `working`
- memory capture -> `success`
- other processed Telegram event -> `success`

Career Command Telegram commands write a second command-specific status after
command handling:

- read-only commands such as `/career status` and `/career tracker` -> `success`
- `/career scout_preview` after completion -> `success`
- `/career save`, `/career draft`, `/career approve`, `/career reject` success -> `success`
- missing user choices such as `/career save` without rows -> `waiting_for_approval`
- command failures -> `error`

Telegram replies are unchanged except for the additional local status writes.

## Future ACE Consumption

Future Tux/cat desktop companion:

- read `current.json`
- map `state` to posture/animation
- map `severity` to visual urgency
- display `title` and `message` as local status text

Future Inspection Cabinet:

- read `history/`
- show a timeline of ARI activity
- correlate `event_id` and `command` with Telegram events, Career Command
  operations, approvals, and future content intake

Future dashboards and intake surfaces:

- read `current.json` for compact ambient status
- read `history/` for operator review and demos

## Safety Boundaries

The status layer is local-first and file-backed.

It does not:

- execute work
- send messages
- apply to jobs
- contact anyone externally
- read `.env`
- store Telegram bot tokens
- store API keys
- create a new source of truth for ARI state

It only records concise local status for ACE surfaces.
