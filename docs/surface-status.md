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
  serializable preview, and the companion renders that preview in a local
  floating desktop window.
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

## Tux Desktop Companion

The Tux companion is the first local desktop ACE surface. It is read-only:
ARI owns and writes status, and Tux only polls `current.json` through the
existing Tux status adapter.

It renders frames from the existing local Tux asset package, polls status every
1.5 seconds by default, maps ARI state to the canonical Tux animation, and shows
a compact status bubble:

```text
working · running
ARI is running a local task.
```

Launch it locally:

```text
ari surface tux companion
```

Dry-run without opening a GUI:

```text
ari surface tux companion --dry-run
```

Useful options:

```text
ari surface tux companion --asset-root "/custom/tux"
ari surface tux companion --status-dir data/surface/status
ari surface tux companion --poll-interval 1
ari surface tux companion --click-target http://127.0.0.1:3000
ari surface tux companion --no-bubble
ari surface tux companion --debug
```

Environment configuration:

```text
ARI_TUX_ASSET_ROOT=/custom/tux
ARI_SURFACE_STATUS_DIR=/custom/status
ARI_TUX_CLICK_TARGET=http://127.0.0.1:3000
```

Click behavior:

- Single click toggles the status bubble.
- Double click opens `--click-target` or `ARI_TUX_CLICK_TARGET`.
- If no click target is configured, double click is a no-op and logs:
  `No ARI_TUX_CLICK_TARGET configured.`

Smoke flow:

```text
ari surface status set --state working --summary "ARI is running a local task." --source smoke
ari surface tux preview
ari surface tux companion --dry-run
ari surface tux companion
```

While the companion is running, update status from another terminal:

```text
ari surface status set --state waiting_for_approval --summary "Codex needs approval." --source smoke
ari surface status set --state success --summary "Task completed." --source smoke
```

Known limitations:

- The MVP uses Python Tkinter rather than a packaged macOS app.
- Transparent window behavior depends on host Tk support.
- Double click only opens an explicitly configured target.
- GUI behavior is intentionally smoke-tested locally; unit tests cover
  non-GUI config, status, frame discovery, and dry-run logic.

Next polish steps:

- Package as a launchable macOS app or menu-bar helper.
- Add drag-to-position persistence if ARI needs it.
- Add richer Inspection Cabinet linking after that local surface is stable.

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

Launch the read-only Tux desktop companion:

```text
ari surface tux companion
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
- write ARI status from the Tux companion

It records concise local status for ACE surfaces to inspect.
