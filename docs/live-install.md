# Live Install

The ARI that answers my messages never runs from a development checkout. It runs from
a release: a clone checked out at one commit, with its own Python environment and hub build.
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
| `ari-live install` | Checks out the commit, builds its environment and the hub, runs the tests, and only then switches `current`. A failed build leaves the live ARI unchanged. |
| `ari-live rollback` | Switches `current` back to the previous release. |
| `ari-live status` | Shows the live release and whether the poller, API, and hub are running. |
| `ari-live connect-apple` | Asks macOS for Reminders and Calendar access for ARI's helper, then switches the connection on. |
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

## Reminders and Calendar

ARI reaches Apple Reminders and Calendar through a small EventKit helper
(`tools/ari-eventkit`), built to `~/ARI/bin/ari-eventkit`. macOS ties the permission to
that exact build, so an install rebuilds it only when its source changes. ARI writes
reminders only to the GET DONE list and adds events to the ARI calendar unless told
otherwise. Both sync through iCloud, so a timed reminder goes off on the iPhone even
while the Mac sleeps. The connection is off until `ari-live connect-apple` succeeds,
which keeps tests and development checkouts away from the real lists.

GET DONE also works as an inbox. Whatever Alec adds there himself, with no connection or
while the Mac sleeps, ARI notices within a minute of running and texts him the new items,
asking whether to act on them now. It never asks about items it wrote itself (it keeps
their ids in `~/ARI/state/get-done-own.json`) and holds the question through quiet hours.

## Controlling the Mac from the phone

`ari-live connect-mac` lets ARI act on this Mac when Alec texts it: open an app or a
web link, quit an app, run one of his Shortcuts by name, set the volume, play or skip
music, turn the display off (which locks it), keep the Mac awake for a while, and say
what's open. Each action is a fixed command with Alec's words passed as arguments, never
a script built from them, and ARI acts only when he asks in that message. macOS asks
once, on the Mac, the first time ARI controls a given app (Spotify, Music, an app it
quits). The switch is `ARI_MAC_CONTROL=1` in `~/ARI/ari.env`.

## The desktop pet

`ari-live install` also builds ARI's desktop pet into `~/Applications/ARI Pet.app` when
its source changes, and `ari-live setup` starts it at login. See
[desktop-pet.md](desktop-pet.md).
