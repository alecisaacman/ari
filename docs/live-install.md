# Live Install

The ARI that answers my messages never runs from a development checkout. It runs from
a release: an export of one commit, with its own Python environment and hub build.
Work in progress can't reach it; an update goes live only when it's finished and its
tests pass.

```text
~/ARI/runtime/
  releases/20261028-091500-81f0ad9/   one commit, built and tested
  releases/...                        the last three are kept
  current -> releases/...             what's live
  logs/
```

`scripts/ari-live` manages it:

| Command | What it does |
|---|---|
| `ari-live install` | Exports the commit, builds its environment and the hub, runs the tests, and only then switches `current`. A failed build leaves the live ARI unchanged. |
| `ari-live rollback` | Switches `current` back to the previous release. |
| `ari-live status` | Shows the live release and whether the poller, API, and hub are running. |
| `ari-live setup` | Points ARI's launchd jobs at `current`. Run once, and again if the jobs change. |
| `ari-live hub open` | Starts ARI's API and the hub if they aren't running, and opens the hub. |
| `ari-live hub stop` | Stops them. |

The iMessage poller starts fresh every 10 seconds, so it picks up a new release on its
next poll. The API and hub restart on a switch only if they were running.

## The hub, on demand

The hub doesn't run at login. "ARI Hub" in `~/Applications` runs `ari-live hub open`;
open it from Spotlight, the Dock, or a keyboard shortcut. The hub listens on
`localhost:3737` only, and ARI's API on `localhost:8787`. The hub's login password is
`ARI_UI_PASSWORD` in `~/ARI/ari.env`; its sessions are kept in `~/ARI/hub`, so updates
don't sign me out.
