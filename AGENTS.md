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
- Update architecture docs when a change materially affects topology, state shape, persistence, routines, or surface responsibilities.
- Preserve explainability. ARI should be able to explain why a signal, alert, or surfaced item exists.

## Delivery Priorities

- Build the spine first: shared state, persistence, events, routines, and explainable signals.
- Avoid overbuilding voice, advanced integrations, or surface polish during early milestones.
- Prefer durable choices that are easy to reorganize later.
