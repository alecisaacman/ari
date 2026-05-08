# ARI Repository Instructions

These instructions apply to all future Codex or agent runs in this repository.

## Source Of Truth

- Treat `docs/` as the architecture source of truth.
- If code and docs diverge, either bring code back into alignment or update the docs in the same change.
- Do not preserve legacy local structure by default. This repository is the canonical source of truth for ARI.

## System Rules

- ARI is the only outward identity.
- ACE is the internal doctrine shaping ARI behavior.
- Maintain one canonical shared state model across CLI, API, hub, notifications, and future surfaces.
- Avoid duplicating business logic across surfaces. Put shared logic in packages.
- Favor modular, typed, testable code over clever shortcuts.

## Change Discipline

- Keep changes small, coherent, and reviewable.
- Prefer additive or local refactors over sweeping rewrites unless explicitly requested.
- Default to the smallest durable complete integration: complete the bounded product behavior described in the prompt while preserving architecture discipline.
- Do not prematurely narrow work to schemas, stubs, placeholders, or proof-of-concept files when the requested outcome is a working vertical path.
- For concrete integration prompts, include code, docs, tests, validation, and the working command or surface behavior unless explicitly told to plan only.
- Update architecture docs when a change materially affects topology, state shape, persistence, routines, or surface responsibilities.
- Preserve explainability. ARI should be able to explain why a signal, alert, or surfaced item exists.

## Delivery Priorities

- Build the spine first: shared state, persistence, events, routines, and explainable signals.
- Avoid overbuilding voice, advanced integrations, or surface polish during early milestones.
- Prefer durable choices that are easy to reorganize later.
- Prefer connecting existing working systems into ARI/ACE over recreating them.

## ARI / ACE Product Model

- ARI owns the brain, authority, state, memory, tools, and approval rules.
- ACE owns surfaces, presence, control, and visibility.
- Telegram is the current ACE phone surface.
- Dashboards are ACE visual surfaces.
- Future desktop companions are ACE ambient status surfaces.
- Codex is the implementation operator, not the ARI brain.
- OpenAI APIs are reasoning and tool-use layers, not systems of record.

## Career Command Boundary

Career Command currently exists as a working prototype at `~/code/openai-dev-sandbox`.

Do not rebuild Career Command, migrate it into `ari-canonical`, or create a
parallel job-search engine unless explicitly asked.

When integrating Career Command:
- inspect and use the existing sandbox files
- build a clean adapter rather than copying the engine
- expose useful controls through Telegram or another ACE surface
- preserve strict approval boundaries
- do not automatically apply to jobs
- do not automatically send emails
- do not automatically send LinkedIn messages
- do not contact anyone externally
- do not allow arbitrary shell execution from Telegram
- do not read, expose, or commit secrets, `.env` files, or runtime data
