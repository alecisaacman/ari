# ARI System

ARI v1 is the private local-first ARI runtime. ACE is the browser, phone, voice, and trigger access layer around it.

## Today and ARI

The hub has no brain of its own. It is a window into ARI's one brain
(`ari_core/brain.py`, the same one iMessage reaches), read live from ari-api's
`/brain/panel`, in two tabs:

- **Today**, for anyone signed in: the chat with ARI (laid out like Messages), the
  day's calendar, GET DONE, reminders, what is waiting for approval, and what ARI
  noticed.
- **ARI**, for its creator: what ARI wants to build, its latest morning and night
  reviews, open loops, spend, what it remembers, notes, the iMessage conversation,
  skills, and, under the hood, the systems read models.

The chat box sends each message to `/brain/messages`, which runs the same
conversation logic as iMessage (`ari_core/conversation.py`): "ARI stop",
"ARI spend", "ARI review", "yes"/"no" for proposals, and everything else to the
brain, under the same budget and loop breaker. The hub keeps its own conversation
thread and shares everything else, because memory, loops, and state are ARI's
records. `/api/trigger` and `/api/voice/input` (with a browser transcript) reach ARI
the same way. In subprocess bridge mode the hub uses `ari api brain panel` and
`ari api brain message` instead.

Run ari-api for the hub to see inside ARI. It reads `ANTHROPIC_API_KEY` from
`~/ARI/ari.env`.

## ARI systems dashboard

Below Inside ARI, the read-only systems dashboard reads the ARI-owned `/overview` read model when `ari-api` is available and
falls back to a clearly labeled static shell when it is not. It displays ARI
doctrine, skill status, readiness surfaces, pending authority surfaces,
coding-loop chain surfaces, memory surfaces, self-documentation surfaces, and
system-health gaps. Summary counts for pending approvals, recent coding-loop
results, and lifecycle lessons are shown only from the ARI-owned overview model;
unavailable counts are labeled as partial. The pending approval detail panel reads
the ARI-owned `/overview/pending-approvals` model and displays approval ids,
source, reason, proposed goal/action summary, and created time when available.
The coding-loop chain detail panel reads `/overview/coding-loop-chains` and
displays recent result ids, goals, terminal statuses, chain depth, approval
counts, retry execution counts, and inspection hints. The lifecycle lessons
panel reads `/overview/lifecycle-lessons` and displays compact lesson summaries,
source ids, confidence, importance, tags, and inspection hints from ARI-owned
memory blocks. The self-documentation artifact panel reads
`/overview/self-documentation` and displays persisted ContentSeed and
ContentPackage summaries, readiness status, proof/redaction counts, and
inspection hints from ARI-owned storage. The content ideas panel reads
`/overview/content-ideas` and displays ARI-owned creator-content options,
priority, risk, platform fit, proof counts, redaction counts, and inspection
hints without generating, recording, editing, or publishing anything.

The shell does not approve, reject, execute, advance chains, mutate memory,
create skills, generate content, record, edit, upload, publish, call external
services, or own independent state. Future controls must call ARI backend
authority surfaces; this page only establishes the read-only product surface.

## What ships in v1

- Responsive ARI interface through the ACE shell
- Shared-password browser login
- Concurrent private sessions across devices and browsers
- Token-protected `/api/trigger` endpoint for iOS Shortcuts
- Local SQLite memory and task storage
- Chat with ARI's brain, and a live view inside it
- Voice input through browser speech recognition

## Stack

- Next.js App Router
- TypeScript
- Node built-in SQLite via `node:sqlite`
- HTTP-only signed session cookies

## Quick start

1. Install dependencies:

```bash
npm install
```

2. Create local env:

```bash
cp .env.example .env.local
```

3. Set at least:

- `ARI_UI_PASSWORD`
- `ARI_TRIGGER_TOKEN`
- `ARI_AUTH_SECRET`

4. Start locally on this machine only:

```bash
npm run dev
```

5. For phone or tablet access on your local network, use the LAN bind:

```bash
npm run build
npm run start:lan
```

Open `http://localhost:3000` on the host machine or `http://YOUR-LAN-IP:3000` from another device on the same network.

For the most reliable phone demo path, prefer `npm run start:lan` over the development server.

## Session behavior

- The password opens the Today side. Touch ID (a passkey) opens everything: that
  session is the creator's.
- The first passkey is set up from a password session, on the ARI tab. After that,
  only the creator can add another. A passkey never leaves the device; the hub keeps
  its public key (`passkeys` table) and single-use challenges that expire in five
  minutes.
- Each login creates its own device-local session cookie, and logging out clears
  only that device's session.

## iOS Shortcuts

Use `POST /api/trigger` with:

- Header: `Authorization: Bearer YOUR_ARI_TRIGGER_TOKEN`
- Content-Type: `application/json`
- Body:

```json
{
  "text": "Remind me at 5 to buy eggs, limes, and coffee"
}
```

Example response:

```json
{
  "reply": "I'll text you at 5:00 PM today: buy eggs, limes, and coffee.",
  "status": "ok"
}
```

Shortcut setup:

1. Create a `Get Contents of URL` action.
2. Set method to `POST`.
3. Set URL to `http://YOUR-LAN-IP:3000/api/trigger`.
4. Add header `Authorization` with value `Bearer YOUR_ARI_TRIGGER_TOKEN`.
5. Send JSON with a `text` field.
6. Read the `reply` field from the response.

## Voice behavior

- The browser recognizes speech and sends the transcript to ARI as a message.
- The hub has no server-side speech provider.

## Workspace changes

The hub doesn't change files itself. ARI's brain proposes a workspace change, ARI
asks Alec, and an approved change runs once through ARI's execution gateway, in
the folder set by `ARI_EXECUTION_ROOT`.

## Future upgrades

- stronger auth and user/device trust
- HTTPS or tunnel-based remote access
- broader tool permissions
- background agents and multi-agent execution
