# Desktop Pets

Each service has a pet that lives on top of the desktop, apart from its app: ARI's
owl and Claude's golden retriever. They are small Mac apps built from one program
(`tools/ari-pet`), one app bundle per character, floating above other windows on every
desktop, with no Dock icon. Clicking a pet opens its app: the owl opens the hub, the
retriever opens Claude.

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

## Claude's retriever

Claude's pet reads Claude's own local session files (`~/.claude/projects`), not ARI's
records. It works (tongue out, wagging, thinking dots) while Claude is mid-task,
perks up with a red dot when Claude has finished and is waiting, says Claude's last
reply in a bubble, lies down with sad eyes when Claude hits a usage limit, and
sleeps when the Claude app is closed or it's late. It is `~/Applications/Claude
Pet.app`, started at login the same way.

### Photo poses

Claude's retriever is meant to be photorealistic. The eight poses are generated as
photos (prompts in `tools/ari-pet/art/claude/PROMPTS.md`), then
`tools/ari-pet/import-art.sh` lifts each dog out of its background with Apple's Vision
subject lifting and files it in `tools/ari-pet/art/claude/`. `ari-live install`
bundles them into Claude Pet. The pet shows the photo for the moment (sitting, panting
while Claude works, alert when Claude waits, asleep, sad at a usage limit, lifted,
leaping, startled), mirrored to face the way it's dragged, with breathing, bounce, and
sway on top. Until the photos exist, it draws the dog instead.
