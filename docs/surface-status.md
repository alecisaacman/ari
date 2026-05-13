# ARI Surface Status Layer

The Surface Status layer is the first shared local status contract for ACE
surfaces. ARI owns this status. ACE surfaces consume it.

This is not a desktop companion, dashboard feature, Telegram brain, or Sleep
Window integration. It is a small ARI-owned read model that answers: what is ARI
doing right now?

## Ownership

- ARI is the brain and source of truth for the status.
- ACE surfaces read the status and render it.
- Tux is a read-only desktop ACE surface consumer. The adapter produces a
  serializable preview; it does not create a desktop window.
- Telegram may read or publish ambient status later, but it does not own the
  status contract.
- Dashboard and Sleep Window are consumers only. They must not become status
  owners or parallel state systems.

## Files

Default local paths:

```text
data/surface/status/current.json
data/surface/status/history/*.json
```

`current.json` is the latest status for lightweight consumers. `history/`
keeps append-only snapshots for debugging, demos, dashboards, and future
Inspection Cabinet timelines.

The location can be overridden with:

```text
ARI_SURFACE_STATUS_DIR=/custom/local/path
```

## Canonical Model

The canonical implementation lives in:

```text
services/ari-core/src/ari_core/surface_status.py
```

Shape:

```json
{
  "state": "idle",
  "role": "ARI",
  "source": "system",
  "summary": "ARI is idle.",
  "event_id": "evt_...",
  "task_id": null,
  "updated_at": "2026-05-12T00:00:00Z",
  "metadata": {}
}
```

Supported states:

```text
idle
routing
working
reviewing
waiting_for_approval
blocked
error
success
```

Writes use temporary files and `os.replace` so local file consumers do not read
partially written JSON.

## Initial Tux Mapping

Tux assets are reusable. The read-only adapter maps the current ARI status to
the expected Tux animation state:

```text
idle -> idle
routing -> jumping
working -> running
reviewing -> review
waiting_for_approval -> waiting
blocked -> failed
error -> failed
success -> waving
```

The adapter lives in:

```text
services/ari-core/src/ari_core/tux_status.py
```

It reads `current.json`, applies the canonical mapping above, and validates the
local Tux asset package without making network calls. The default asset root is:

```text
/Users/alecisaacman/ARI (codex)/pet-runs/tux
```

The asset root can be overridden with `ARI_TUX_ASSET_ROOT` or the CLI
`--asset-root` option. Required local assets are:

```text
frames/<tux_state>/
frames/frames-manifest.json
final/spritesheet.png or final/spritesheet.webp
```

## CLI

Show current status:

```text
ari surface status show
```

Set current status:

```text
ari surface status set --state working --summary "Testing Tux status"
```

Both commands operate on local files only. They make no network calls.

Show the read-only Tux preview for the current status:

```text
ari surface tux preview
```

JSON output for future UI consumers:

```text
ari surface tux preview --json
```

## Safety Boundaries

The status layer does not:

- execute work
- send messages
- contact external services
- read `.env`
- store tokens or secrets
- create a second source of truth for ARI
- embed Tux in the dashboard
- connect Tux to Sleep Window
- create a macOS app, overlay, or floating desktop window

It records concise local status for ACE surfaces to inspect.
