# ARI System

ARI v1 is the private local-first ARI runtime. ACE is the browser, phone, voice, and trigger access layer around it.

## Current ACE dashboard shell

The default home page is now the first minimal ACE read-only dashboard shell.
It is static and diagnostic: it displays ARI doctrine, skill status, readiness
surfaces, pending authority surfaces, coding-loop chain surfaces, memory
surfaces, self-documentation surfaces, and system-health gaps.

The shell does not approve, reject, execute, advance chains, mutate memory,
create skills, call external services, or own independent state. Future controls
must call ARI backend authority surfaces; this page only establishes the
read-only product surface.

## What ships in v1

- Responsive ARI interface through the ACE shell
- Shared-password browser login
- Concurrent private sessions across devices and browsers
- Token-protected `/api/trigger` endpoint for iOS Shortcuts
- Local SQLite memory and task storage
- Deterministic no-key fallback mode
- Hosted model upgrade path
- Workspace-scoped file tools
- Voice input and output with browser fallbacks

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

- One private user can stay logged in on multiple devices and browsers at the same time.
- Each login creates its own device-local session cookie.
- Logging out clears only the current device session.
- Future stronger auth can replace this without changing the rest of the runtime.

## Hosted model upgrade

ARI boots without any model key. If `ARI_OPENAI_API_KEY` is set, the runtime upgrades from deterministic fallback mode to hosted text generation. If the transcription and TTS models are available, the voice endpoints upgrade too.

## iOS Shortcuts

Use `POST /api/trigger` with:

- Header: `Authorization: Bearer YOUR_ARI_TRIGGER_TOKEN`
- Content-Type: `application/json`
- Body:

```json
{
  "text": "Save a note called Grocery list: eggs, limes, coffee"
}
```

Example response:

```json
{
  "reply": "Saved note \"Grocery list\".",
  "conversationId": "b6b7...",
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

- If a hosted speech provider is configured, ARI can transcribe audio server-side and return speech audio.
- If not, the browser falls back to speech recognition and speech synthesis when available.

## Workspace file tools

ARI can read, list, and write files only inside:

`services/ari-hub/workspace`

No delete or broader project file access ships in v1.

## Future upgrades

- Ollama or other local LLM providers
- stronger auth and user/device trust
- HTTPS or tunnel-based remote access
- broader tool permissions
- background agents and multi-agent execution
