# ARI Repository Instructions

These instructions apply to all future Codex or agent runs in this repository.
Claude Code is the master builder and owns architectural decisions; Codex is a
managed specialist invoked for narrow, well-contracted work. Read this whole
file before touching anything — the permission-model section in particular
documents a real, tested failure mode, not a theoretical concern.

## What ARI Is

ARI is not a chatbot. It is a persistent local executive agent: a governed
decision/authority/execution loop with durable memory, that is meant to
operate continuously with reduced manual intervention, not just respond
when spoken to. Every design choice should optimize for that end state, not
for the smallest thing that works today.

## Current Architecture (as of 2026-06-19)

- **Spine**: Python 3.12 monorepo. `packages/` = ari-state (Pydantic models),
  ari-memory (SQLAlchemy repositories, one class per table), ari-events,
  ari-routines, ari-signals (rule-based signal engine), ari-cli. `services/` =
  ari-core (the governed controller/authority/executor loop + the brain),
  ari-api, ari-hub (secondary "look under the hood" surface — NOT dead code,
  intentionally kept per the product vision; just not the primary surface).
- **Brain** (`services/ari-core/src/ari_core/brain.py`): the single
  intelligence layer. Claude (Anthropic API), tool-use grounded against real
  ari-memory state — it never invents facts about open loops/state, it calls
  read tools. `NO_REPLY` sentinel convention: the brain explicitly chooses
  silence for non-actionable input rather than always replying.
- **iMessage pipeline**: two decoupled processes, not one. See "Permission
  model" below for why.
- **Persistence**: Postgres via SQLAlchemy + Alembic. `ConversationState`
  table holds brain memory per channel (replaced fragile JSON files).
- **Process supervision**: launchd agents (`scripts/com.ari.*.plist`),
  installed under `~/Library/LaunchAgents/`.
- **Governance**: `state/PAUSED` flag (checked by every entry point via
  `exit_if_paused`) + `scripts/ari-killswitch.sh` (unloads every
  `com.ari.*.plist`). Resume via `scripts/ari-resume.sh`. Concurrency: every
  scheduled entry point that mutates shared state must wrap its main work in
  `exit_if_already_running` (`scripts/_ari_common.py`) — a real overlapping-run
  race was caught and fixed here on 2026-06-19.

## Permission Model — Read Before Touching Anything iMessage-Related

`~/Library/Messages/chat.db` requires macOS Full Disk Access (FDA). This
repo's solution is **not** "grant FDA to Python" or "grant FDA to bash" —
both were tried and rejected:

- Granting FDA to a Homebrew-versioned Python binary breaks on every
  `brew upgrade` (the path includes the version number).
- Granting FDA to `/bin/bash` was rejected as too broad (every script on the
  whole machine would inherit disk-wide read access).
- **Empirically confirmed by direct testing**: macOS's TCC check for Full
  Disk Access attributes the request to the **top-level process launchd
  spawned**, not to whichever leaf binary actually calls `open()`. A
  `launchd -> bash -> sqlite3` chain was denied even with `sqlite3` itself
  individually granted FDA. A bare `launchd -> sqlite3` chain succeeded.

The fix: `scripts/com.ari.imessage-dump.plist` runs `/usr/bin/sqlite3` as
launchd's **literal direct child** — no bash, no Python in between — and
dumps the self-thread to `state/imessage-dump.tsv` every 60s. FDA is granted
to `/usr/bin/sqlite3` only, forever (it's Apple-signed, never moves).
Everything else — `imessage-poll.sh`, `imessage-ingest.py`, the brain — reads
that plain file and never touches `chat.db` and never needs FDA.

**Do not "simplify" this back into a single process that calls sqlite3 from
inside Python or bash.** It will fail silently in the worst way: it works
when you test it manually in a terminal (which has its own FDA grant via
Terminal.app), and fails only under real launchd-scheduled execution — i.e.
it will look fine in review and break in production. If you need to change
this pipeline, test by triggering the actual installed launchd job
(`launchctl kickstart -k gui/$(id -u)/com.ari.imessage-poll`) and reading
`logs/imessage-poll.log`, not by running the script directly in a shell.

**Corollary — the self-echo loop (caught and fixed 2026-06-19)**: because the
dump is a periodic snapshot (60s) rather than a live query, there is no
rowid available at "I just sent a reply" time that reflects that reply —
the dump literally cannot contain it yet. An earlier version tried to
"advance the cursor past our own reply" by reading the current max rowid
from the same dump; this can never work (the dump is always stale relative
to a reply just sent), and the result was a self-sustaining loop: ARI's
reply becomes visible on the *next* dump refresh, gets treated as new input
from Alec, ARI replies to its own reply, that reply becomes visible on the
following refresh, forever. The fix is content-based, not rowid-based:
`_recent_sent_texts()` in `imessage-ingest.py` recognizes incoming text that
exactly matches one of ARI's own recently-sent replies (drawn from the
persisted conversation history) and skips it, regardless of dump timing.
**If you touch the iMessage cursor/echo logic, do not reintroduce a
rowid-based "advance past my own reply" mechanism — it is structurally
incompatible with the dump architecture.** See
`tests/unit/test_imessage_ingest.py` for the regression coverage.

## Source Of Truth

- Treat `docs/` as the architecture source of truth; this file as the
  operating/ownership rules for agents working in the repo.
- If code and docs diverge, either bring code back into alignment or update
  the docs in the same change.
- Do not preserve legacy local structure by default. This repository is the
  canonical source of truth for ARI.

## Ownership Boundaries — What Codex May and May Not Touch

**Claude-only (do not hand to Codex, do not let Codex modify unreviewed):**
- `services/ari-core/src/ari_core/{brain,controller,authority,executor}.py`
  — the governed decision/trust boundary. Context about prior bugs here
  (dry-run that wasn't dry, duplicate-loop bugs, self-message feedback
  loops) lives in the building session, not in this repo — changes here
  need that history, not just the current diff.
- Anything in `migrations/` or `packages/ari-state/src/ari_state/models.py` /
  `packages/ari-memory/src/ari_memory/tables.py` (schema). Schema mistakes
  are expensive against a running Postgres instance with real production
  data already in it.
- `scripts/_ari_common.py`, `scripts/ari-killswitch.sh`,
  `scripts/ari-resume.sh`, any `com.ari.*.plist`, and anything else in the
  permission model described above.

**Good Codex hand-off candidates (narrow, contract-driven, low blast radius):**
- New repository classes in `ari-memory/repositories.py` following the
  existing pattern (one class per table, `get`/`upsert`, a private
  `_to_model` converter) — given an exact method signature to implement.
- New signals in `ari-signals` following the existing rule-based shape.
- New `ari-cli` subcommands.
- `services/ari-hub` UI work, once redesigned, against a defined API contract.
- Test-writing against existing modules, especially adversarial edge cases.
- Security review of any code that shells out or interpolates strings
  toward an external interpreter (subprocess, AppleScript, SQL).

**Hard rule**: Codex never runs an Alembic migration and never merges
directly to main. Claude Code reviews every Codex diff — convention
adherence, correctness, and (for anything touching a subprocess/SQL/
AppleScript boundary) a security pass — before it lands.

## Conventions To Follow

- `ARIModel` base (`use_enum_values=True, extra="forbid"`) for all
  ari-state Pydantic models.
- Repository pattern: one class per table, `get`/`upsert`, private
  `_to_model`.
- Every automation script's `__main__` block: `exit_if_paused(name)` first,
  then (if it mutates shared state on a schedule) wrap the run in
  `exit_if_already_running(name)`, then `run_guarded(name, run, ...)`.
- `.env` via `python-dotenv`; never echo secrets in logs or output.

## System Rules

- ARI is the only outward identity.
- ACE is the internal doctrine shaping ARI behavior.
- Maintain one canonical shared state model across CLI, API, hub,
  notifications, and the brain.
- Avoid duplicating business logic across surfaces. Put shared logic in
  packages.
- Favor modular, typed, testable code over clever shortcuts.

## Change Discipline

- Keep changes small, coherent, and reviewable.
- Prefer additive or local refactors over sweeping rewrites unless
  explicitly requested.
- Update architecture docs when a change materially affects topology,
  state shape, persistence, routines, or surface responsibilities.
- Preserve explainability. ARI should be able to explain why a signal,
  alert, or surfaced item exists — and, for the brain, ground every claim
  about state in an actual tool call, never invent.

## Delivery Priorities (current phase)

The spine (shared state, persistence, events, routines, explainable
signals) is built. Current phase priorities, in order: continuous reliable
operation, durable process supervision, strong logging/observability/
recovery, memory/context continuity, executive-level usefulness, reduced
manual intervention, and a clear, auditable permission model with working
kill switches — all ahead of new user-facing features. The next major
capability is proactive/ambient behavior (ARI surfacing priorities and
research unprompted, not just responding) — this is a deliberate
architectural decision, not yet built; see the building session for the
decision/trade-off framing before starting it.
