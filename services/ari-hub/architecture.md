# ARI v1 Architecture

## Layers

### Interface Layer (ACE)
- Next.js App Router UI
- single-user login gate
- responsive chat and voice controls

### Voice Layer
- browser `MediaRecorder`
- hosted STT and TTS when configured
- browser speech fallbacks when not configured

### Agent Core
- one `runTurn()` orchestration loop
- rule-first intent detection
- provider-backed conversational generation when available
- delegation scaffolding for future sub-agents

### Memory Layer
- SQLite persistence in `runtime/ari.db`
- conversations, messages, memories, tasks, tool runs
- simple keyword and recency retrieval

### Tool Layer
- registry-based tool execution
- note, task, and workspace file tools
- workspace path sandboxing

### Model Layer
- hosted provider
- deterministic fallback provider
- Ollama scaffold

### API Layer
- route handlers for chat, voice, trigger, and health
- session cookie auth for browser
- bearer token auth for external triggers

## Design choices

### Why Next.js as both UI and API host
One runtime keeps local setup simple and gives a clean path from browser UI to private HTTP endpoints without splitting deployment concerns too early.

### Why built-in SQLite
Node now ships a reliable SQLite API, which keeps persistence local, readable, and dependency-light.

### Why deterministic fallback
ARI should remain useful without pretending to be more intelligent than it is. The fallback path handles memory, tasks, notes, and safe tools with explicit limits.

### Why private auth is lightweight
ARI is a single-user local system in v1. Shared-secret browser login and bearer tokens are enough to secure the surface while preserving a straightforward upgrade path to stronger auth later.

## Upgrade seams

- Replace shared-secret auth with device-aware or identity-backed auth
- Swap hosted text provider or add Ollama without changing the agent or tool contracts
- Move from inline delegation to background workers or separate sub-agents
- Expand the tool boundary beyond `workspace/` once trust and policy are stronger
