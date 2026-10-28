# ARI's Desktop Pet

ARI has a pet that lives on top of the desktop, apart from the hub: a small owl. It is
its own little Mac app (`tools/ari-pet`), floating above other windows on every
desktop, with no Dock icon.

- **Drag it anywhere.** It leans into a sideways drag, flaps when lifted, and flings its
  wings out when dragged down. It remembers where you leave it.
- **Click it** to open the hub. **Hover** for a one-line status. **Right-click** to open
  the hub, ask what's going on, hide it for an hour, or quit.
- **Its moods show ARI's state:** idle (breathing, blinking), thinking while ARI handles
  a message, perked up with a red dot when something needs me, asleep when ARI is
  paused or late at night, gray and droopy with an empty battery when the budget or
  Anthropic credits run out, and dozing gray when ARI hasn't checked in for a few
  minutes.
- **New messages from ARI** appear in a bubble above it, even with the hub closed.

The pet never calls a model or the API. ARI's iMessage poller writes
`~/ARI/state/pet-status.json` on every poll (`ari_core/pet_status.py`), and the pet
reads it every two seconds. `ari-live install` rebuilds the pet into
`~/Applications/ARI Pet.app` when its source changes; `ari-live setup` starts it at
login. `ARI Pet --snapshot DIR` draws every pose to PNGs for checking the art.

The same app is meant to carry other characters later, one per service.
