# ARI Skill Inventory

## Purpose

ARI tracks skills so the brain can understand a goal, determine what bounded
capability is needed, check whether that capability exists, invoke it through
the shared ARI spine, verify the result, and learn from the outcome.

This document is a status inventory, not a runtime registry. It does not enable
dynamic loading, generic orchestration, or imported skill execution.

## Current Native Skills

### `ari.native.coding_loop`

- Status: active
- Maturity: first mature ARI-native skill
- Manifest: `docs/skills/coding-loop-skill.md`
- Contract: `docs/skills/ari-native-skill-contract.md`

What it does:

- Performs one bounded coding-loop action.
- Validates plans through ARI execution policy.
- Executes through ARI-owned bounded execution paths.
- Verifies outcomes.
- Persists coding-loop results, execution runs, and retry approvals.
- Supports approval, rejection, one-step approved retry execution, post-run
  review, continuation decisions, chain inspection, and compact lifecycle
  memory capture.

What it does not do:

- It does not make ARI a coding assistant only.
- It does not provide broad multi-step autonomy.
- It does not approve automatically.
- It does not run arbitrary shell commands.
- It does not own memory, authority, approval, planning, or execution policy
  independently.
- It does not act as a generic skill framework or registry.

Current active native skill count: 1.

## Candidate Future Native Skills

These are candidates only. They are not implemented, active, imported, or
runtime-loadable.

| Candidate skill id | Status | Likely purpose | Required authority boundary | Verification requirement |
| --- | --- | --- | --- | --- |
| `ari.native.document_pdf_processing` | candidate / not implemented | Extract, summarize, transform, and verify document or PDF files. | Approval before file mutation, export, deletion, or disclosure of private content. | Render/readback checks, file existence checks, extracted text checks, and summary evidence links. |
| `ari.native.research_gathering` | candidate / not implemented | Gather sources, summarize findings, and create cited research briefs. | Approval before external network access, paid services, or storing sensitive research. | Source citations, timestamped retrieval metadata, quote limits, and confidence notes. |
| `ari.native.local_file_organization` | candidate / not implemented | Inspect local files and propose safe organization actions. | Approval before moves, renames, deletes, copies, or broad filesystem traversal. | Dry-run plans, path existence checks, before/after manifests, and reversible operation evidence. |
| `ari.native.spreadsheet_analysis` | candidate / not implemented | Analyze tabular files, compute summaries, and produce verified outputs. | Approval before modifying source sheets or exporting derived files. | Formula/readback checks, row/column counts, sample validations, and chart/data consistency checks. |
| `ari.native.email_calendar_triage` | candidate / not implemented | Summarize inbox/calendar state and propose replies, scheduling actions, or follow-ups. | Explicit approval before reading connected accounts, sending messages, modifying events, or storing private content. | Connector readback, drafted-action review, event/message ids, and no-send/no-mutate dry runs. |
| `ari.native.browser_inspection` | candidate / not implemented | Inspect web or local browser state for evidence and debugging. | Approval before external browsing, login/session use, form submission, downloads, or state mutation. | URL/title snapshots, screenshot/evidence references, and no-click/no-submit dry runs where possible. |
| `ari.native.self_improvement_task_generation` | candidate / not implemented | Convert repeated failures or capability gaps into inspectable improvement tasks. | Approval before queueing implementation work or dispatching a builder. | Deduped improvement records, evidence links, priority rationale, and completion criteria. |
| `ari.native.planner_quality_goal_decomposition` | candidate / not implemented | Break broad goals into bounded skill invocations and safe next actions. | Approval before invoking skills with side effects or escalating to external models. | Bounded decomposition records, skill-fit rationale, rejected alternatives, and stop conditions. |
| `ari.native.self_documentation` | designed / not implemented | Convert ARI activity into factual build summaries, content seeds, demo scripts, shot lists, voiceover drafts, and future approval-gated media packages. | Approval before recording, exporting public-facing media, publishing, using external services, or including sensitive data. | Commit/test/doc/run evidence, current capability checks, no-secret/no-private-data review, and no false-claim validation. |

Stage 1 readiness for `ari.native.self_documentation` is tracked in
`docs/skills/self-documentation-stage-1-readiness.md`.

## Imported Or Wrapped Skills

No imported or open-source skills are active yet.

Future imported skills must be wrapped under ARI. They may provide tool
capabilities, but they must not own:

- memory
- authority
- approval
- planning
- execution policy
- persistence
- inspection
- explanation

Imported tools must expose capabilities, risks, required approvals, validation
hooks, verification hooks, memory effects, and inspection payloads before ARI
can use them.

## Skill Lifecycle States

- `candidate`: named as a possible future skill; not designed or active.
- `designed`: manifest and readiness gates exist; no runtime capability yet.
- `prototype`: limited implementation exists behind tests and explicit bounds.
- `active`: callable through ARI's shared spine with validation, verification,
  persistence, inspection, and memory effects.
- `deprecated`: retained for historical inspection but no longer preferred.
- `blocked`: cannot proceed because authority, verification, safety, or product
  boundaries are unresolved.

## Readiness Gates

A skill may become active only when:

- a manifest exists
- authority requirements are defined
- approval requirements are defined
- validation rules are deterministic and fail-closed
- verification methods are defined
- memory effects are compact and explicit
- inspection output is defined
- tests prove it does not bypass ARI
- tests prove non-execution paths do not mutate state
- tests prove unsafe inputs fail closed

## Anti-Drift Warning

The coding loop is powerful, but it is not the whole ARI architecture.

Do not build future interfaces as coding-loop-only dashboards. ACE should
consume ARI skill inventory, state, approvals, memory, and explanations from the
canonical brain, not become a coding-loop shell.

Do not let imported agents become competing brains. ARI may wrap tools and
skills, but ARI owns goal interpretation, authority, memory, execution policy,
verification, inspection, explanation, and learning.

Read-only ACE dashboard work is governed by
`docs/ace/read-only-dashboard-contract.md`.
