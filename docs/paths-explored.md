# Paths Explored

ARI's history includes directions that were built, learned from, and set aside. Their
branches stay on GitHub as the original record. Most of their useful work was folded
into `main` on 2026-06-22 by the consolidation in PR #6; the branches themselves are
not being developed.

| Branch | When | What it tried | Where it stands |
|---|---|---|---|
| `import/ace-prototype-phase` | Apr 2026 | First convergence of the brain, API, and hub into one repository (PR #1, v0.9). | Merged. Its one extra commit defined the autonomous coding loop objective. |
| `chore/cooldown-docs-and-helpers` | Apr–May 2026 | An autonomous coding loop: an OpenAI Responses planner, a canonical execution tool registry, execution approvals, and approval-aware retry proposals. | Folded into `main` by PR #6. Coding stays bounded and supervised; ARI's brain now runs on Claude. |
| `chore/ruff-cleanup-runtime-tests` | Apr–May 2026 | The same coding-loop line, plus coding-loop chains, continuation policy, overview read models, and the first read-only ACE dashboard. | Folded into `main` by PR #6. The read-only dashboard is now the hub's systems view. |
| `feature/telegram-gateway` | Apr–May 2026 | Telegram as the main way to talk to ARI, alongside Career Command, a Tux desktop companion, and a surface status layer. | Folded into `main` by PR #6. Telegram is kept as an earlier surface; iMessage replaced it as the primary one. |
| `preserve-governance-layer` | Jun 2026 | Preserving the governance layer (authority, executor, controller, approvals), skill audit logging, the kill switch, company research for job applications, and an early iMessage ingest with launchd jobs. | Folded into `main` by PR #6, except the iMessage prototype, which was rebuilt as `packages/ari-imessage-gateway`. Personal identifiers were removed from this branch's history on 2026-10-28. |
| `feat/imessage-channel-clean` | Jun 2026 | A first iMessage channel bridge and runtime cycle (PR #7). | Superseded by the iMessage surface on the single brain (Oct 2026). PR #7 closed. |
| `feat/canonical-kill-switch`, `feat/imessage-channel`, `integration/ari-current-state` | Jun 2026 | The kill switch, an earlier iMessage step, and the consolidation itself (PR #6). | Already part of `main`. |

## What these taught

- **One brain, many surfaces.** Telegram, the hub's own model, and a separate iMessage
  bridge each pulled toward a second brain. ARI now has one conversation path
  (`ari_core/conversation.py`) that every surface uses.
- **Native beats new apps.** iMessage replaced Telegram because it's already where I
  talk.
- **Supervised execution first.** The autonomous coding loop work became the execution
  gateway: proposals, approval in code, one execution, and a durable trail.
