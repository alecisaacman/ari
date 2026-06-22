# iMessage gateway

ARI's primary interaction surface. A self-message thread (you texting yourself) is the
channel: every message in it is treated as input to ARI, and any reply ARI sends back into
that same thread.

## How it works

1. `scripts/com.ari.imessage-dump.plist` (created locally from the `.example` template below)
   is a launchd job that runs `/usr/bin/sqlite3` —
   and only `/usr/bin/sqlite3` — as launchd's **direct child**, every 60 seconds. It dumps
   the self-thread from `~/Library/Messages/chat.db` to a plain file at
   `state/imessage-dump.tsv`. This is the only process that ever touches `chat.db`.
2. The hub's background runtime (`services/ari-hub/src/core/agent/background-runtime.ts`)
   reads that TSV file every cycle (`services/ari-hub/src/core/ari-spine/imessage-bridge.ts`),
   skips anything it's already processed (cursor) or that's an echo of its own last few
   replies, and calls the hub's normal `runTurn()` for anything new — the exact same
   reply-generation path the web chat UI uses.
3. Replies are sent back into the thread via AppleScript (`osascript`), targeting
   Messages.app directly.

## Why the dump job has to be this shape

macOS's TCC (the Full Disk Access gatekeeper) attributes an FDA check to the **top-level
process launchd spawned**, not to whichever leaf binary actually opens the file. Confirmed
by direct testing: a `launchd -> bash -> sqlite3` chain was denied even with sqlite3 itself
individually granted FDA; `launchd -> sqlite3` directly succeeded. So `/usr/bin/sqlite3`
must be launchd's immediate `argv[0]` — no shell, no Python, no Node in between — for the
FDA grant to take effect. Every other piece of this pipeline (the hub, in TypeScript) only
ever reads the plain TSV file the dump job writes, and never needs Full Disk Access itself.

## One-time manual setup (cannot be done from inside this environment)

1. **Create your local plist from the template**:
   ```
   cp scripts/com.ari.imessage-dump.plist.example scripts/com.ari.imessage-dump.plist
   ```
   Edit `scripts/com.ari.imessage-dump.plist` and fill in, for your machine only:
   - `/Users/REPLACE_WITH_MAC_USERNAME/...` → your actual local paths (dump TSV and log paths)
   - `REPLACE_WITH_SELF_THREAD_PHONE_OR_HANDLE` → your self-thread phone number/handle
   - `REPLACE_WITH_SELF_THREAD_APPLE_ID_OR_EMAIL` → your self-thread Apple ID/iCloud email

   **Never commit the filled-in `scripts/com.ari.imessage-dump.plist`** — it contains your
   real local username, paths, phone number, and Apple ID. Only the `.example` template
   with placeholders belongs in the repo; `.gitignore` already excludes the real file.
2. **Grant Full Disk Access to `/usr/bin/sqlite3`**: System Settings → Privacy & Security →
   Full Disk Access → add `/usr/bin/sqlite3` (not Terminal, not Python, not Node — the
   binary itself).
3. **Load the dump job**:
   ```
   cp scripts/com.ari.imessage-dump.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.ari.imessage-dump.plist
   ```
   Confirm it's producing output: `tail -f state/imessage-dump.tsv` after sending yourself
   a message in the self-thread (within ~60s).
4. **Grant Automation permission** for sending replies: System Settings → Privacy &
   Security → Automation → allow whatever process runs the hub (`node`, or your terminal
   app if running `npm run dev` interactively) to control Messages.

Until both are granted, the hub will see no dump file (or a stale one) and skip the
iMessage step of its cycle entirely — every other part of the hub keeps working normally.

## Configuration

The self-thread identifiers are baked directly into your local plist's SQL `WHERE` clause
(a single-operator local-first system doesn't need this to be templated beyond the
`.example` placeholders). Update both the phone number and Apple ID email there if either
changes — Messages can split your self-conversation across more than one chat row
depending on which identity composed a given message, so both must be listed for ARI to
see the whole thread.

## Local runtime artifacts (never committed)

`state/imessage-dump.tsv` (the dump file), anything under `logs/`, and the filled-in
`scripts/com.ari.imessage-dump.plist` are all local runtime artifacts excluded by
`.gitignore`. They contain real message content and personal identifiers and must stay
local to your machine.
